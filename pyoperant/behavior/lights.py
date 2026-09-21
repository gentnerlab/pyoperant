# -*- coding: utf-8 -*-
"""
lights.py — Light-schedule experiment with optional free food and passive
song recording.

Running without any of the optional blocks in config.json
-----------------------------------------------------------
Behaviour is identical to the original Lights class: the state machine
cycles idle → sleep (lights off) → idle, respecting the light_schedule.

Free food (see free_food_schedule -- independent feature, not documented
further here)

Enabling song recording
------------------------
Add a ``song_recording`` block to config.json.  The Lights class will then:

  * Turn lights off at the start of the dark period.
  * Run noise-floor calibration for the chamber (~45 s, bird not vocalising).
  * Record vocalizations throughout the light period via the panel's
    microphone (panel.microphone -- see pyoperant.hwio.AudioInput and
    local_pi_revd.py).
  * Run a brief drift-correction pass just before lights come back on.

Minimal config.json with recording enabled -- everything under
song_recording has a sensible default except enabled itself, and paths
default relative to the bird's own experiment_path (the same
DATAPATH/<subject> directory every other behavior already writes into)::

    {
        "light_schedule": [["06:00", "20:00"]],
        "song_recording": {
            "enabled": true
        }
    }

Full song_recording block, showing every overridable key and its default::

    {
        "song_recording": {
            "enabled": true,
            "monitor": {
                "sample_rate": 48000,
                "chunk_duration": 0.1,
                "freq_low": 1000, "freq_high": 10000,
                "pre_roll": 1.0, "post_roll": 2.0,
                "min_clip_duration": 0.5,
                "output_dir": "<experiment_path>/recordings",
                "log_csv":    "<experiment_path>/detections.csv"
            },
            "gate": {
                "rms_floor": 0.003,
                "min_band_energy_ratio": 0.10,
                "threshold": 0.45,
                "weight_flatness":  0.35,
                "weight_onset":     0.25,
                "weight_harmonic":  0.25,
                "weight_band":      0.15
            },
            "frame_smoother": {
                "window_size": 10,
                "onset_k": 6,
                "sustain_k": 4
            },
            "noise_model": {
                "enabled": true,
                "calibration_duration_s": 45,
                "sensitivity_k": 4.0,
                "snr_score_threshold": 0.001,
                "model_path": "<experiment_path>/noise_model.npz",
                "drift_correction_duration_s": 10,
                "drift_alpha": 0.2
            }
        }
    }

All sub-keys are optional; only override what differs from the defaults
above. See pyoperant.song_recording's package docstring for the detection
pipeline itself.
"""

import os
import threading
import logging

from pyoperant import utils, components
from pyoperant.behavior import base

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — read the nested song_recording config
# ---------------------------------------------------------------------------

def _sr_cfg(parameters):
    """Return the song_recording sub-dict, or {} if absent/disabled."""
    sr = parameters.get('song_recording', {})
    if not sr.get('enabled', False):
        return {}
    return sr


def _recording_enabled(parameters):
    return bool(_sr_cfg(parameters))


def _noise_model_enabled(parameters):
    sr = _sr_cfg(parameters)
    if not sr:
        return False
    return sr.get('noise_model', {}).get('enabled', True)


# ---------------------------------------------------------------------------
# Lights
# ---------------------------------------------------------------------------

class Lights(base.BaseExp):
    """A session-less behavior: just keeps the house light on `light_schedule`,
    optionally offers the bird free access to the hopper on
    `free_food_schedule`, and optionally records the bird's vocalizations
    via the panel's microphone (see the module docstring's `song_recording`
    config block). Useful for holding a bird on a light/feeding schedule
    (with or without passive acoustic monitoring) between real experiments,
    without running any trials.

    Free food and song recording are both independent, optional, and
    disabled by default -- omit either block from config.json and Lights
    behaves as if that feature didn't exist. When song_recording is
    enabled, `_run_idle` routes to the normal BaseExp session state
    (`session_pre/main/post`) for the rest of the light period; when it
    isn't, that branch is never taken and the idle loop behaves exactly as
    it always has.
    """
    def __init__(self,  *args, **kwargs):
        super(Lights, self).__init__(*args, **kwargs)
        self.req_panel_attr.append('reward')

        # Monitor thread state (song recording only)
        self._monitor_thread = None
        self._monitor_stop   = threading.Event()
        self._gate      = None
        self._extractor = None
        self._smoother  = None
        # Prevents calibration running more than once per dark period
        self._calibrated_this_night = False

        if _recording_enabled(self.parameters):
            self.log.info('Song recording enabled.')
        else:
            self.log.info(
                'Song recording disabled '
                '(no song_recording block in config or enabled=false).'
            )

    # ------------------------------------------------------------------
    # Panel reset — original behaviour preserved
    # ------------------------------------------------------------------

    def panel_reset(self):
        try:
            self.panel.reset()
        except components.HopperWontDropError:
            pass

    # ------------------------------------------------------------------
    # Idle — light/free-food/(recording session) routing
    # ------------------------------------------------------------------

    def _run_idle(self):
        """Same as BaseExp._run_idle, except:
        - the free-food check doesn't require check_session_schedule() --
          Lights has no session concept of its own, so that gate would
          otherwise make free_food_schedule silently inert here (fixed in
          e50aff6, before song recording existed).
        - song recording gets its own branch, also independent of
          check_session_schedule(), for the same reason: routes into the
          normal BaseExp session state (session_pre/main/post below) for
          as long as light_schedule says lights should be on, so the
          monitor thread runs the whole light period."""
        self.log.debug('Starting _run_idle')
        if self.check_light_schedule() == False:
            return 'sleep'
        elif self._check_free_food_block():
            return 'free_food_block'
        elif _recording_enabled(self.parameters):
            return 'session'
        else:
            self.panel_reset()
            self.log.debug('idling...')
            utils.wait(self.parameters['idle_poll_interval'])
            return 'idle'

    def _free_food(self):
        """A solenoid shouldn't be held energized continuously, so
        BaseExp._free_food cycles it up/down for the duration of the
        schedule -- that's still correct here for a solenoid hopper. A
        servo can safely hold the raised position, though, so use a
        continuous raise/hold/lower instead of cycling it.

        Falls back to the solenoid-style cycling behavior if the panel's
        hopper actuator can't be determined."""
        if getattr(getattr(self.panel, 'hopper', None), '_actuator', None) == 'servo':
            return self._free_food_continuous()
        return super(Lights, self)._free_food()

    def _free_food_continuous(self):
        """Servo-hopper free food: raise once, hold for as long as
        free_food_schedule stays active, then lower once."""
        self.log.debug('Starting continuous free food (servo hopper)')
        try:
            self.panel.hopper.up()
        except components.HopperWontComeUpError:
            self.log.warning("Hopper did not come up for free food")
            return 'idle'

        while self._check_free_food_block():
            utils.wait(self.parameters['idle_poll_interval'])

        try:
            self.panel.hopper.down()
        except components.HopperWontDropError:
            self.log.warning("Hopper did not go down after free food")

        return 'idle'

    # ------------------------------------------------------------------
    # Sleep hooks — dark period (song recording only; no-ops otherwise)
    # ------------------------------------------------------------------

    def sleep_pre(self):
        self._calibrated_this_night = False
        self.log.debug('lights off. going to sleep...')
        return 'main'

    def sleep_main(self):
        """Same as BaseExp.sleep_main, plus a one-time-per-night noise
        calibration pass when song recording is enabled."""
        self.log.debug('sleeping...')
        self.panel.house_light.off()

        if _recording_enabled(self.parameters) and not self._calibrated_this_night:
            self._run_calibration()
            self._calibrated_this_night = True

        utils.wait(self.parameters['idle_poll_interval'])
        if self.check_light_schedule() == False:
            return 'main'
        else:
            return 'post'

    def sleep_post(self):
        """Same as BaseExp.sleep_post, plus a drift-correction pass just
        before lights-on when song recording is enabled."""
        if _recording_enabled(self.parameters):
            self._run_drift_correction()

        self.log.debug('ending sleep')
        self.panel.house_light.on()
        self.init_summary()
        return None

    # ------------------------------------------------------------------
    # Session hooks — light period (song recording only; unreachable
    # otherwise, since _run_idle only returns 'session' when recording is
    # enabled)
    # ------------------------------------------------------------------

    def session_pre(self):
        self._build_pipeline()
        self._start_monitor()
        return 'main'

    def session_main(self):
        """Keep the monitor running for as long as light_schedule says
        lights should be on; return 'post' (which stops it) at lights-off."""
        utils.wait(self.parameters['idle_poll_interval'])
        if self.check_light_schedule():
            return 'main'
        else:
            return 'post'

    def session_post(self):
        self._stop_monitor()
        return None

    def emergency_shutdown(self):
        """Called from scripts/behave's signal handler on SIGTERM/SIGINT --
        see BaseExp.emergency_shutdown(). _stop_monitor() is already safe
        to call unconditionally (no-ops if the monitor was never started),
        so this needs no extra guarding. Without this, killing the process
        while the monitor's daemon thread holds an open PortAudio stream
        skips cleanup entirely -- sys.exit() only unwinds the main thread,
        and a daemon thread gets no chance to run its own `finally:
        audio_input.close()` before the process dies with it. Confirmed
        live, 2026-09-10 (see project_vocal_recorder memory): this is the
        leading suspect for a real USB-audio device wedge that cost a
        production box ~6 hours of missed recording the next morning."""
        self._stop_monitor()

    # ------------------------------------------------------------------
    # Noise model helpers
    # ------------------------------------------------------------------

    def _microphone(self):
        """Return panel.microphone, or None with a clear log message if
        this panel doesn't have one -- song recording is optional and not
        every panel configures a microphone (e.g. Rev C boards, or a bare
        test panel), so this must degrade gracefully rather than crash the
        light-schedule duty Lights always needs to keep doing."""
        mic = getattr(self.panel, 'microphone', None)
        if mic is None:
            self.log.error(
                'song_recording is enabled but this panel has no '
                'microphone configured (self.panel.microphone) -- '
                'recording will be skipped.'
            )
        return mic

    def _run_calibration(self):
        """Record ambient audio and build the per-bin noise floor model.

        Called once per dark period, immediately after lights go off.
        The bird should not be vocalising at this point.
        """
        if not _noise_model_enabled(self.parameters):
            self.log.info('Noise model disabled; skipping calibration.')
            return

        mic = self._microphone()
        if mic is None:
            return

        from pyoperant.song_recording.noise_model import calibrate

        sr   = _sr_cfg(self.parameters)
        nm   = sr.get('noise_model', {})
        dur  = nm.get('calibration_duration_s', 45)
        path = self._noise_model_path()

        self.log.info(
            'Starting noise calibration: %.0f s. '
            'Lights are off; bird should not be vocalising.', dur
        )
        try:
            model = calibrate(
                audio_input   = mic,
                duration_s    = dur,
                chunk_dur     = sr.get('monitor', {}).get('chunk_duration', 0.1),
                freq_low      = sr.get('monitor', {}).get('freq_low',  1000),
                freq_high     = sr.get('monitor', {}).get('freq_high', 10000),
                sensitivity_k = nm.get('sensitivity_k', 4.0),
                device_id     = self.parameters.get('subject', ''),
                progress      = False,
            )
            model.save(path)
            self.log.info('Calibration complete. Model saved → %s', path)

            # Attach to an already-running gate (e.g. first night after
            # the monitor has been started mid-session).
            if self._gate is not None:
                self._gate.noise_model = model
                self.log.info('Updated running gate with new noise model.')

        except Exception as exc:
            self.log.error('Noise calibration failed: %s', exc, exc_info=True)

    def _run_drift_correction(self):
        """Apply a short exponential update to the saved noise model.

        Called once per dark period, just before lights come back on.
        """
        if not _noise_model_enabled(self.parameters):
            return

        mic = self._microphone()
        if mic is None:
            return

        sr    = _sr_cfg(self.parameters)
        nm    = sr.get('noise_model', {})
        path  = self._noise_model_path()
        dur   = nm.get('drift_correction_duration_s', 10)
        alpha = nm.get('drift_alpha', 0.2)

        if not os.path.exists(path):
            self.log.info(
                'No saved model at %s; skipping drift correction.', path
            )
            return

        from pyoperant.song_recording.noise_model import NoiseModel, update_drift

        self.log.info(
            'Running drift correction: %.0f s, alpha=%.2f.', dur, alpha
        )
        try:
            model = NoiseModel.load(path)
            model = update_drift(
                model,
                audio_input = mic,
                duration_s  = dur,
                alpha       = alpha,
                progress    = False,
            )
            model.save(path)
            self.log.info('Drift correction complete. Model updated → %s', path)
        except Exception as exc:
            self.log.error('Drift correction failed: %s', exc, exc_info=True)

    # ------------------------------------------------------------------
    # Config-derived paths
    # ------------------------------------------------------------------

    def _output_dir(self):
        sr = _sr_cfg(self.parameters)
        return sr.get('monitor', {}).get(
            'output_dir', os.path.join(self.parameters['experiment_path'], 'recordings'))

    def _log_csv_path(self):
        sr = _sr_cfg(self.parameters)
        return sr.get('monitor', {}).get(
            'log_csv', os.path.join(self.parameters['experiment_path'], 'detections.csv'))

    def _noise_model_path(self):
        sr = _sr_cfg(self.parameters)
        return sr.get('noise_model', {}).get(
            'model_path', os.path.join(self.parameters['experiment_path'], 'noise_model.npz'))

    # ------------------------------------------------------------------
    # Detection pipeline
    # ------------------------------------------------------------------

    def _build_pipeline(self):
        """Build gate, feature extractor, and smoother from config.

        Flattens the nested song_recording config into the flat-dict
        format expected by the factory functions in
        pyoperant.song_recording.gate / .smoother.
        """
        sr  = _sr_cfg(self.parameters)
        mon = sr.get('monitor', {})

        flat_cfg = {
            'sample_rate':    mon.get('sample_rate', 48000),
            'freq_low':       mon.get('freq_low',  1000),
            'freq_high':      mon.get('freq_high', 10000),
            'chunk_duration': mon.get('chunk_duration', 0.1),
            'gate':           sr.get('gate', {}),
            'frame_smoother': sr.get('frame_smoother', {}),
            'score_smoother': sr.get('score_smoother', {}),
            'variability':    sr.get('variability', {}),
            'noise_model':    dict(sr.get('noise_model', {}),
                                    model_path=self._noise_model_path()),
        }

        try:
            from pyoperant.song_recording.gate import make_gate_from_config
            from pyoperant.song_recording.smoother import CombinedSmoother

            self._gate, self._extractor = make_gate_from_config(flat_cfg)
            self._smoother = CombinedSmoother.from_config_dict(flat_cfg)

            nm_status = 'loaded' if self._gate.has_noise_model else \
                        'not loaded — using fixed RMS fallback'
            self.log.info(
                'Detection pipeline ready. Noise model: %s.', nm_status
            )
        except ImportError as exc:
            self.log.error(
                'Could not import pyoperant.song_recording (%s). '
                'Recording will be disabled this session.', exc
            )
            self._gate = self._extractor = self._smoother = None

    # ------------------------------------------------------------------
    # Monitor thread management
    # ------------------------------------------------------------------

    def _start_monitor(self):
        """Start the SongMonitor in a background daemon thread."""
        if self._gate is None:
            self.log.warning(
                'Detection pipeline not ready; monitor will not start.'
            )
            return

        mic = self._microphone()
        if mic is None:
            return

        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target = self._monitor_run,
            args   = (mic,),
            name   = 'song-monitor',
            daemon = True,
        )
        self._monitor_thread.start()
        self.log.info('Monitor thread started.')

    def _monitor_run(self, mic):
        """Thread target: run SongMonitor until _monitor_stop is set.

        Any failure here (including the mic device not being found/opened
        by PyAudioInterface) is caught and logged, not raised -- Lights
        must keep controlling the light schedule regardless of whether
        recording itself is working."""
        sr  = _sr_cfg(self.parameters)
        mon = sr.get('monitor', {})
        flat_cfg = {
            'sample_rate':       mon.get('sample_rate', 48000),
            'chunk_duration':    mon.get('chunk_duration', 0.1),
            'capture_chunk_multiplier': mon.get('capture_chunk_multiplier', 1),
            'freq_low':          mon.get('freq_low',  1000),
            'freq_high':         mon.get('freq_high', 10000),
            'pre_roll':          mon.get('pre_roll', 1.0),
            'post_roll':         mon.get('post_roll', 2.0),
            'min_clip_duration': mon.get('min_clip_duration', 0.5),
            'precursor_max_duration': mon.get('precursor_max_duration', 3.0),
            'precursor_min_score':    mon.get('precursor_min_score', 0.55),
            'precursor_grace_period': mon.get('precursor_grace_period', 8.0),
            'device_watchdog_timeout':          mon.get('device_watchdog_timeout', 5.0),
            'device_reconnect_backoff_initial': mon.get('device_reconnect_backoff_initial', 1.0),
            'device_reconnect_backoff_max':      mon.get('device_reconnect_backoff_max', 30.0),
            'startup_retry_giveup_after':        mon.get('startup_retry_giveup_after', 300.0),
            'output_dir':        self._output_dir(),
            'log_csv':           self._log_csv_path(),
        }
        try:
            from pyoperant.song_recording.monitor import SongMonitor
            monitor = SongMonitor(
                cfg         = flat_cfg,
                audio_input = mic,
                gate        = self._gate,
                extractor   = self._extractor,
                smoother    = self._smoother,
                stop_event  = self._monitor_stop,
            )
            monitor.run()
        except Exception as exc:
            self.log.error(
                'Monitor thread crashed: %s', exc, exc_info=True
            )

    def _stop_monitor(self):
        """Signal the monitor to stop and block until it exits."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            return
        self.log.info('Stopping monitor thread...')
        self._monitor_stop.set()
        self._monitor_thread.join(timeout=10.0)
        if self._monitor_thread.is_alive():
            self.log.warning('Monitor thread did not stop within 10 s.')
        else:
            self.log.info('Monitor thread stopped cleanly.')
        self._monitor_thread = None
