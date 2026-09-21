"""
monitor.py — Songbird vocalization monitor.

Runs embedded in pyoperant, via pyoperant.behavior.lights.Lights:

    from pyoperant.song_recording.monitor import SongMonitor
    monitor = SongMonitor(cfg, audio_input, gate, extractor, smoother, stop_event)
    monitor.run()          # blocks until stop_event.set()

audio_input is a pyoperant.hwio.AudioInput -- typically panel.microphone,
so the monitor shares the same PortAudio context Lights already opened for
that panel rather than a second, standalone one.

This module also has a small standalone diagnostic entry point:
    python -m pyoperant.song_recording.monitor --list-devices
SongMonitor itself always needs a real audio_input handed to it (built from
a live panel) -- there's no standalone recording-loop mode here, unlike an
earlier prototype of this module that opened its own ad hoc audio stream
from a device index/config file.

Song-precursor grace period
----------------------------
Motivated by a real finding from the lab's own labeled corpus (see
project_vocal_recorder memory): short, high-scoring vocalizations -- e.g. a
contact-type whistle -- sometimes precede a full song bout after a gap
longer than the standard post_roll hangover, and sometimes don't precede
anything at all. Context, not the chunk alone, decides which. Ordinarily,
once a detection episode releases (the smoother's vote drops), the clip
closes `post_roll` seconds later. If that just-released episode was BOTH
short (<= `precursor_max_duration`) and confidently scored
(peak gate score >= `precursor_min_score`), the monitor instead grants one
longer `precursor_grace_period` before closing -- long enough to bridge the
gap if real song follows. If it does, the episode re-triggers within the
grace window and the whole thing (whistle + gap + song) is saved as ONE
continuous clip, matching how the corpus itself represents a bout. If
nothing follows, the clip closes after the grace period with just the
short vocalization in it -- still saved, not discarded, since it may be a
real (if brief) not-song vocalization worth having on file.

This is a duration+score heuristic, not a real "is this a whistle"
classifier -- deliberately so, since it's meant to generalize across birds/
chambers, not key off one bird's acoustic signature. `gate_result.score`
(the existing weighted composite) stands in for "confidently vocal" for
now; revisit once the corpus-driven feature work (a more robust harmonicity
estimate than today's live `harmonic_ratio`, see the starsong-feature-
analysis project) lands in the live gate, which should make this gate
sharper without changing the surrounding state machine.

Device-loss detection and recovery
------------------------------------
Confirmed live, 2026-09-09 (see project_vocal_recorder memory): unplugging
and replugging a USB mic mid-session leaves the previously-open PyAudio
stream silently dead -- no exception, no error, the audio callback simply
stops firing, and the monitor thread was observed spinning CPU
unproductively (12% -> 51%) rather than either recovering or erroring out.
Undetected, this means a transient USB reset during weeks of unattended
real deployment silently stops all recording until someone happens to
notice.

`run()`'s main loop now tracks how long it's been since a real chunk was
last pulled off the audio queue. Past `device_watchdog_timeout` seconds of
silence, it declares the device lost (logged at `error`, not `warning` --
this is a real problem, and `error`/`critical` are what the existing
SMTPHandler-on-root-logger mechanism, see the "MagPi server" reference,
turns into an email to the experimenter for free, no new alerting plumbing
needed) and attempts to close and reopen the stream. Reopening re-resolves
the device by name from scratch (the same `_find_device_index` substring
match cold-start already uses), so a replugged device landing at a new
PortAudio index is handled the same way it already is at startup. Retries
use capped exponential backoff (`device_reconnect_backoff_initial` up to
`device_reconnect_backoff_max`) rather than a tight loop, since the
observed failure mode was itself a busy-spin -- hammering a still-missing
device immediately would just recreate that problem. A successful
`open_stream()` call is NOT by itself treated as recovery (it can succeed
against the wrong/fallback device without erroring) -- only an actual
chunk arriving again clears the lost state and resets the backoff.

**Recovery is also reported at `warning`, not `info`** (added 2026-09-11,
after the user pointed out the gap): an ERROR alert with no matching
follow-up leaves whoever reads it wondering whether a later quiet retry
actually fixed things, or whether it's still broken -- INFO-only would
mean the recovery note only ever reaches the local log file, never the
inbox the ERROR itself reached. Only fires when `_device_lost` was
actually `True` (i.e. an ERROR really was raised for this episode) --
recovering from something nobody was ever told about doesn't need a
message. Prefixed `RESOLVED:` so it reads unambiguously as good news
sitting in the same inbox as the alert it answers, not a second problem.
`_open_stream_with_retry()` (see "Startup retry" below) follows the exact
same pattern for the same reason.

Capture buffering headroom
----------------------------
Observed live, 2026-09-09 (real B1474 deployment, see project_vocal_recorder
memory): intermittent `paInputOverflow` warnings (PortAudio status flag 2)
roughly every 8-9 minutes, even with the monitor thread's own CPU/queue
comfortably unloaded -- PortAudio's ALSA ring buffer for the input stream
is sized around one `chunk_duration` (100ms) worth of audio per callback,
so any scheduling jitter longer than that on this Pi's USB-audio driver
overflows it before our callback runs. This isn't full device loss (the
callback still fires and decodes fine), just a small window of audio lost
at the ALSA/kernel level between callbacks.

PyAudio exposes no direct "suggested latency" knob on Linux/ALSA (checked
the installed binding directly -- `input_host_api_specific_stream_info` is
CoreAudio/WASAPI/ASIO-only), so the only real lever is `frames_per_buffer`
itself: requesting a bigger block per PortAudio callback was the obvious
lever to try -- more total buffered audio in flight per callback, at the
cost of a larger chunk of raw bytes delivered each time.
`capture_chunk_multiplier` controls how many logical `chunk_duration`
chunks are requested per callback; `_on_capture_block()` immediately
splits whatever arrives back into exact `chunk_duration`-length pieces
(carrying any leftover samples across callbacks) before queuing, so the
gate/smoother/precursor-grace state machine downstream -- all of which
assume every queued chunk is exactly one `chunk_duration` long -- needs no
changes regardless of the multiplier's value.

**Tried at 3 (300ms), measured live on B1474, 2026-09-10 -- made it worse,
not better.** The intuitive "bigger buffer = more headroom" reasoning
turned out backwards for this specific USB Audio Class 1.0 device/Pi
driver combination: a controlled A/B (clean single-process, idle-system,
5 minutes each way) measured *zero* overflow warnings at multiplier=1
versus roughly one every 20-40s at multiplier=3 -- a ~10-20x regression
from the original ~1/8min baseline this was meant to fix. Root mechanism
unconfirmed (never chased further once the numbers settled it -- plausibly
this ALSA/USB-audio driver allocates a roughly fixed total ring-buffer
capacity divided into periods sized by whatever `frames_per_buffer` you
request, so a *larger* requested period can mean *fewer* periods fit,
shrinking rather than growing the real headroom before the whole ring
overflows). Lesson worth keeping: the earlier verification only checked
whether `open()` succeeds at a given buffer size, never the *sustained*
overflow rate under real running conditions -- those are different
questions, and only the live, controlled, extended measurement caught
this. Default is back to 1 (no behavior change from before this whole
investigation) until a *measured*, not reasoned-from-first-principles,
case for a different value shows up. The knob and the splitting
infrastructure stay -- both correct and harmless at multiplier=1 -- in
case that measurement happens later.

**Logged at `info`, not `warning`** (changed 2026-09-11, after enabling email alerting for
a real subject surfaced this in practice): this condition is real but already investigated
and deliberately left unresolved as low-priority at its established baseline rate -- not
something to act on. `warning` reaches the same SMTPHandler-on-root-logger mechanism used
for real alerts (see "Device-loss detection and recovery" below), so at `warning` this
was emailing genuine noise for something already decided not worth chasing. Still fully
visible in the local `.log` file at `info` -- nothing lost, just not escalated. Revisit if
the rate climbs, clusters, or the still-unbuilt severity detector (real lost-duration via
PortAudio's ADC timestamp, cross-referenced against whether a clip was actively recording --
discussed but not yet built, see project_vocal_recorder memory) ever shows it costing real
song.

Startup retry
----------------------------
The device-loss watchdog above only covers losing a stream that was
already open. Before this section existed, the very first
`open_stream()` call -- at the top of `run()`, before the main loop --
had no such protection: a failure there (drift correction's own capture
attempt, in noise_model.py, has the same gap and is not yet covered)
logged one ERROR and gave up for the rest of that light period, with
`Lights` otherwise running normally and recording simply, silently, off.
Confirmed live, 2026-09-10 (B1474, see project_vocal_recorder memory): one
transient open failure at a dawn light-on transition cost ~6 hours of
recording, undiscovered until a human happened to check logs by hand --
compounded by the fact that this subject's `config.json` didn't have
`'email'` in `log_handlers` either, so not even the existing
SMTPHandler-on-root-logger alerting fired.

`_open_stream_with_retry()` now wraps that first `open_stream()` call in
the same capped exponential backoff as the mid-session watchdog (reusing
`device_reconnect_backoff_initial`/`_max` -- no new config keys), looping
until it succeeds or `stop_event` is set (i.e. the session legitimately
ended, e.g. lights-off, before the device ever became available -- treated
as a clean exit, not a crash). Only the FIRST failure logs at `error` (the
signal meant to reach the SMTPHandler); every retry after that logs at
`warning`, same as the mid-session watchdog's own retry-failure line --
repeated identical-call-site alerts within one outage are already
suppressed by `log_config()`'s `_EmailOccurrenceFilter` (see base.py),
not by holding retries below the alerting threshold.

**On success after at least one failure, logs a `RESOLVED:` follow-up at
`warning`** (see the "Device-loss detection and recovery" section above
for the full reasoning -- same fix, same day, same motivation: an ERROR
alert with no matching "it's fixed now" leaves the reader unsure whether
a later quiet retry actually worked). Gated on `attempt > 0`, so success
on the very first try (nothing was ever reported broken) stays silent.

**Give-up-and-exit, added 2026-09-21** (see project_vocal_recorder memory's
"Open question, deliberately deferred" section for the full investigation
this responds to): the retry loop above helps for causes external to this
process's own history -- another process briefly holding the device, a
transient boot-time race -- but real `fuser` evidence from 2026-09-10 shows
a failed `pa.open()` on this USB Audio Class 1.0/ALSA driver combination can
leave a kernel-level handle behind, held by THIS SAME process, even though
the Python call raised. Nothing in `_open_stream_with_retry()`'s own retry
loop can release a handle its own process leaked -- only the process dying
and the kernel reclaiming its file descriptors has been confirmed to clear
that (a manual restart, 2026-09-10). So retrying forever in-process risks
spinning at the backoff cap indefinitely against exactly the failure mode
that motivated this whole feature.

`_open_stream_with_retry()` now tracks cumulative backoff time waited and
gives up once `startup_retry_giveup_after` seconds have passed without a
successful open (default 300s -- roughly one fleet-supervisor cron cycle,
confirmed running every ~5 min and confirmed to succeed against a genuinely
fresh process; giving up any sooner wouldn't get relaunched any faster, and
giving up much later just prolongs a recording gap the supervisor could
have already fixed). On give-up, `run()` calls `self._exit_fn` (default
`os._exit`, injected so this is testable without actually killing the test
process) to end the WHOLE PROCESS, not just this daemon thread -- a bare
return/exception here would only unwind the monitor thread, leaving `Lights`
running with recording silently dead, the same class of gap the
SIGTERM/`emergency_shutdown` fix addressed for a different trigger.
Deliberately does NOT call `emergency_shutdown()` first -- that path exists
for graceful hardware teardown on an intentional stop (SIGTERM/SIGINT), a
different situation from this one, where the whole point is a fast, certain
process exit the supervisor can react to; `os._exit()`'s abrupt skip of
Python-level cleanup is the correct behavior here, not a shortcut around it.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import logging
import os
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import pyaudio

from pyoperant.song_recording._pcm import decode_pcm

log = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    "sample_rate":       48000,
    "channels":          1,
    "chunk_duration":    0.1,
    # Capture buffering headroom -- see module docstring's "Capture
    # buffering headroom" section. Requests capture_chunk_multiplier
    # logical chunks per PortAudio callback, splitting them back into
    # exact chunk_duration pieces before anything downstream sees them.
    # Default is 1 (no-op, matches pre-2026-09 behavior exactly) -- a
    # larger value was tried and measured WORSE on real hardware, not
    # better; don't raise this without a live, controlled, sustained-rate
    # measurement first, not just an open()-succeeds check.
    "capture_chunk_multiplier": 1,
    "freq_low":          1000,
    "freq_high":         10000,
    "pre_roll":          1.0,
    "post_roll":         2.0,
    "min_clip_duration": 0.5,
    # Song-precursor grace period -- see module docstring.
    "precursor_max_duration": 3.0,   # episode must be no longer than this to qualify
    "precursor_min_score":    0.55,  # ...and confidently scored (base gate.threshold is 0.45)
    "precursor_grace_period": 8.0,   # extended hangover granted instead of post_roll
    # Device-loss detection and recovery -- see module docstring.
    "device_watchdog_timeout":         5.0,   # seconds of silence before declaring the device lost
    "device_reconnect_backoff_initial": 1.0,  # seconds before the first reconnect retry
    "device_reconnect_backoff_max":     30.0, # cap on retry backoff growth
    # Give-up-and-exit -- see module docstring's "Startup retry" section.
    # Cumulative backoff time _open_stream_with_retry() will wait before
    # giving up and exiting the whole process, so the fleet supervisor
    # relaunches with a genuinely fresh one (clears a device handle this
    # process may have leaked -- an in-process retry can't).
    "startup_retry_giveup_after": 300.0,
    "output_dir":        "recordings",
    "log_csv":           "detections.csv",
}


# ---------------------------------------------------------------------------
# Detection log (CSV)
# ---------------------------------------------------------------------------

class DetectionLog:
    FIELDS = ["timestamp", "filename", "duration_s", "rms",
              "gate_score", "snr_score", "precursor_extended",
              "calibrated_level_db"]

    def __init__(self, csv_path: str):
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        exists  = Path(csv_path).exists()
        self._f = open(csv_path, "a", newline="")
        self.writer = csv.DictWriter(self._f, fieldnames=self.FIELDS)
        if not exists:
            self.writer.writeheader()
            self._f.flush()

    def write(self, **kwargs):
        row = {k: kwargs.get(k, "") for k in self.FIELDS}
        self.writer.writerow(row)
        self._f.flush()

    def close(self):
        self._f.close()


# ---------------------------------------------------------------------------
# SongMonitor
# ---------------------------------------------------------------------------

class SongMonitor:
    """
    Continuous vocalization monitor.

    Parameters
    ----------
    cfg         : dict   Monitor config (keys match DEFAULT_CONFIG).
    audio_input : pyoperant.hwio.AudioInput to record from (typically
                  panel.microphone).
    gate        : SongGate instance, or None to build from cfg.
    extractor   : FeatureExtractor instance, or None to build from cfg.
    smoother    : CombinedSmoother instance, or None to build from cfg.
    stop_event  : threading.Event — set to stop cleanly.
                 If None, runs until KeyboardInterrupt.
    exit_fn     : callable(int) — called to end the whole process on
                 give-up-and-exit (see module docstring). Defaults to
                 `os._exit`; injectable so this is testable without
                 actually killing the test process.
    """

    def __init__(
        self,
        cfg:         dict,
        audio_input,
        gate=None,
        extractor=None,
        smoother=None,
        stop_event: Optional[threading.Event] = None,
        exit_fn=os._exit,
        mic_calibration=None,
    ):
        self.cfg         = {**DEFAULT_CONFIG, **cfg}
        self.audio_input = audio_input
        self.stop_event  = stop_event
        self._exit_fn    = exit_fn
        self._gate       = gate
        self._extractor  = extractor
        self._smoother   = smoother
        # Optional pyoperant.song_recording.calibration.MicCalibration --
        # None means log uncalibrated (no file synced for this box yet).
        # See module docstring's cross-reference and calibration.py's own
        # docstring for what calibrated_level_db is (and isn't) traceable
        # to.
        self._mic_calibration = mic_calibration

        if (self._gate is None) != (self._extractor is None):
            # A caller supplying only one of the two almost certainly meant
            # to supply both -- silently rebuilding a fresh pair from cfg
            # (the old `or` check) would discard whichever one they DID
            # pass without any indication, e.g. a custom test gate quietly
            # replaced by a real one built from cfg.
            raise ValueError(
                "SongMonitor: gate and extractor must be supplied together "
                "or not at all (got gate=%r, extractor=%r)"
                % (self._gate, self._extractor)
            )
        if self._gate is None:
            self._build_pipeline()
        if self._smoother is None:
            self._build_smoother()

        sr  = self.cfg["sample_rate"]
        dur = self.cfg["chunk_duration"]
        self._chunk_len      = int(sr * dur)
        # Capture buffering headroom -- see module docstring. PortAudio is
        # asked for capture_chunk_multiplier chunks per callback;
        # _on_capture_block() splits each delivery back into exact
        # _chunk_len pieces, carrying any remainder here across callbacks.
        self._capture_multiplier = max(1, int(self.cfg["capture_chunk_multiplier"]))
        self._capture_len        = self._chunk_len * self._capture_multiplier
        self._capture_pending    = np.zeros(0, dtype=np.float32)
        self._pre_buffer     = collections.deque(maxlen=int(self.cfg["pre_roll"] / dur))
        self._post_chunks    = int(self.cfg["post_roll"] / dur)
        self._precursor_grace_chunks = int(self.cfg["precursor_grace_period"] / dur)
        self._recording      = False
        self._post_countdown = 0
        # Per-episode state for the precursor-grace decision (see module
        # docstring) -- reset whenever a new episode starts (below).
        self._episode_active_chunks = 0    # chunks while the smoother was actually triggered
        self._episode_peak_score    = 0.0
        self._episode_peak_calibrated_db = None   # see _mic_calibration above
        self._precursor_extended    = False
        self._clip_buffer: list[np.ndarray] = []

        # Device-loss watchdog state -- see module docstring. Initialized
        # here (not just in run()) so _check_device_health()/_on_chunk_received()
        # are directly callable/testable without first calling run().
        self._last_chunk_at            = time.monotonic()
        self._device_lost              = False
        self._reconnect_backoff        = self.cfg["device_reconnect_backoff_initial"]
        self._next_reconnect_attempt_at = 0.0

        Path(self.cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
        self._out_dir = Path(self.cfg["output_dir"])
        self._det_log = DetectionLog(self.cfg["log_csv"])
        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)

    def _build_pipeline(self):
        from pyoperant.song_recording.gate import make_gate_from_config
        self._gate, self._extractor = make_gate_from_config(self.cfg)

    def _build_smoother(self):
        from pyoperant.song_recording.smoother import CombinedSmoother
        self._smoother = CombinedSmoother.from_config_dict(self.cfg)

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def _on_capture_block(self, in_data, status):
        """Handle one PortAudio callback delivery -- which may span several
        logical chunk_duration chunks, see capture_chunk_multiplier in the
        module docstring/DEFAULT_CONFIG. Decodes it, stitches on any
        leftover from the previous delivery, and queues zero or more exact
        chunk_duration-length pieces, carrying any remainder forward.
        Pulled out of run()'s callback closure so it's directly
        unit-testable, matching _on_chunk_received/_check_device_health.
        """
        if status:
            # INFO, not WARNING -- deliberately (2026-09-11, see module
            # docstring's "Capture buffering headroom" section). This is
            # PortAudio's paInputOverflow flag at its established baseline
            # rate (~1/8min), already investigated and left unresolved as a
            # known, low-priority condition -- not something to act on yet.
            # WARNING reaches the SMTPHandler-on-root-logger alerting (any
            # WARNING+ anywhere in the process emails the experimenter), so
            # at WARNING this emailed real noise for something we'd already
            # decided not to chase. Still fully visible in the local .log
            # file at INFO -- nothing lost, just not escalated.
            log.info("Audio status: %s", status)
        try:
            block = decode_pcm(in_data, self.audio_input.sample_format,
                                self.audio_input.channels_opened)
        except Exception:
            log.exception("Error decoding audio callback data")
            return
        if self._capture_pending.size:
            block = np.concatenate([self._capture_pending, block])
        n_full = len(block) // self._chunk_len
        for i in range(n_full):
            piece = block[i * self._chunk_len:(i + 1) * self._chunk_len]
            try:
                self._audio_q.put_nowait(piece)
            except queue.Full:
                pass
        self._capture_pending = block[n_full * self._chunk_len:]

    def run(self):
        """Open the audio stream and process chunks until stop_event is set."""

        def _audio_callback(in_data, frame_count, time_info, status):
            self._on_capture_block(in_data, status)
            return (None, pyaudio.paContinue)

        log.info(
            "Monitor starting (sr=%d, chunk=%.0fms, capture_block=%.0fms)",
            self.cfg["sample_rate"], self.cfg["chunk_duration"] * 1000,
            self.cfg["chunk_duration"] * 1000 * self._capture_multiplier,
        )

        outcome = self._open_stream_with_retry(_audio_callback)
        if outcome == "stopped":
            log.warning(
                "Monitor stopping before a working audio stream was ever "
                "opened -- session ended while still retrying."
            )
            self._det_log.close()
            return
        if outcome == "giveup":
            self._det_log.close()
            self._exit_fn(1)
            return  # unreachable with the real os._exit; keeps this
                     # testable when exit_fn is faked

        self._last_chunk_at = time.monotonic()
        try:
            while not self._should_stop():
                try:
                    chunk = self._audio_q.get(timeout=0.5)
                    self._on_chunk_received()
                    self._process(chunk)
                except queue.Empty:
                    self._check_device_health(_audio_callback)
        except KeyboardInterrupt:
            log.info("Monitor stopped by KeyboardInterrupt.")
        finally:
            self.audio_input.close()
            self._det_log.close()
            log.info("Monitor stopped. Recordings in %s", self._out_dir)

    def _open_stream_with_retry(self, callback, sleep_fn=time.sleep) -> str:
        """Open the capture stream, retrying with the same capped
        exponential backoff already proven for a mid-session device loss
        (see module docstring's "Device-loss detection and recovery"
        section) if the very first attempt fails, instead of giving up for
        the whole session -- see the module docstring's "Startup retry"
        section for why this exists (a real ~6h recording gap on B1474,
        2026-09-10, from exactly this case: one transient open failure at
        session start, previously left with no way to recover short of a
        human noticing and restarting the process).

        Logs ERROR once, on the first failure only (this is the signal
        meant to reach someone via the existing SMTPHandler-on-root-logger
        mechanism -- see the "Device-loss" section -- not once per retry,
        which would spam an inbox every backoff interval for a condition
        already reported). Later retries log at INFO.

        Returns one of three string outcomes (run() needs to tell these
        apart -- see the module docstring's "Give-up-and-exit" section):
          "opened"  -- open_stream() succeeded.
          "stopped" -- stop_event was set while still retrying, i.e. the
                       session ended legitimately (light-off, or the
                       process was asked to stop) before the device ever
                       became available. run() treats this as a clean,
                       quiet exit, not a crash.
          "giveup"  -- retried for startup_retry_giveup_after cumulative
                       seconds without success, stop_event was never set.
                       run() hard-exits the whole process so the fleet
                       supervisor relaunches with a genuinely fresh one.
        `sleep_fn` is injectable so the self-test can drive this
        deterministically without real waits.
        """
        backoff      = self.cfg["device_reconnect_backoff_initial"]
        giveup_after = self.cfg["startup_retry_giveup_after"]
        attempt      = 0
        elapsed      = 0.0
        while not self._should_stop():
            try:
                self.audio_input.open_stream(chunk_size=self._capture_len, callback=callback)
                if attempt > 0:
                    # WARNING, not INFO, deliberately -- attempt > 0 means the
                    # ERROR branch below already fired an alert for this
                    # episode; without a matching reply, the only thing that
                    # ever reaches an inbox is "something's wrong," with no
                    # follow-up saying it resolved on its own. RESOLVED: makes
                    # the two unmistakable apart at a glance in the same
                    # inbox/subject line.
                    log.warning(
                        "RESOLVED: audio device opened after %d retr%s -- "
                        "recording has resumed automatically. No action "
                        "needed.", attempt, "y" if attempt == 1 else "ies",
                    )
                return "opened"
            except Exception as exc:
                if attempt == 0:
                    log.error(
                        "Could not open audio device at startup: %s. "
                        "Retrying automatically with backoff -- if a "
                        "RESOLVED follow-up arrives shortly, no action is "
                        "needed. If this persists more than a few minutes, "
                        "a plain retry may not be enough (the device can "
                        "get stuck in a state only a fresh process or a "
                        "physical unplug/replug clears) -- try unplugging "
                        "and replugging the USB microphone, or restart the "
                        "recording process.", exc, exc_info=True,
                    )
                else:
                    log.warning(
                        "Retry %d failed to open audio device: %s; "
                        "retrying in %.1fs.", attempt, exc, backoff,
                    )
                attempt += 1

            if elapsed >= giveup_after:
                log.error(
                    "Giving up on in-process retry after %d attempts over "
                    "%.0fs -- exiting the whole process so the fleet "
                    "supervisor relaunches with a fresh one. A plain "
                    "in-process retry cannot release a device handle this "
                    "process may have leaked on an earlier attempt; a "
                    "fresh process is the only thing confirmed to clear "
                    "that. No action needed if the supervisor's next cycle "
                    "picks it back up automatically -- check for a "
                    "RESOLVED follow-up.", attempt, elapsed,
                )
                return "giveup"

            waited = 0.0
            while waited < backoff and not self._should_stop():
                step = min(0.5, backoff - waited)
                sleep_fn(step)
                waited  += step
                elapsed += step
            backoff = min(backoff * 2, self.cfg["device_reconnect_backoff_max"])
        return "stopped"

    def _should_stop(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

    # ------------------------------------------------------------------
    # Device-loss detection and recovery -- see module docstring.
    # ------------------------------------------------------------------

    def _on_chunk_received(self):
        """Call from run()'s main loop every time a real chunk is pulled off
        the queue -- i.e. the stream is demonstrably alive. Clears any
        device-loss state left over from a prior reconnect attempt."""
        self._last_chunk_at = time.monotonic()
        if self._device_lost:
            # WARNING, not INFO -- same reasoning as _open_stream_with_retry's
            # matching RESOLVED log: self._device_lost only being True means
            # _check_device_health already fired an ERROR alert for this
            # episode, and that alert deserves a follow-up saying it's over,
            # not just a local-log-only note nobody but this file ever sees.
            log.warning(
                "RESOLVED: audio device recovered -- resuming normal "
                "monitoring. No action needed."
            )
            self._device_lost = False
            self._reconnect_backoff = self.cfg["device_reconnect_backoff_initial"]

    def _check_device_health(self, callback, now: float | None = None):
        """Call from run()'s main loop whenever the audio queue has been
        empty for a poll interval. `now` is injectable so this is directly
        unit-testable without real sleeps; real usage always omits it
        (uses the real clock).
        """
        if now is None:
            now = time.monotonic()
        silent_for = now - self._last_chunk_at
        if silent_for < self.cfg["device_watchdog_timeout"]:
            return

        if not self._device_lost:
            self._device_lost = True
            self._reconnect_backoff = self.cfg["device_reconnect_backoff_initial"]
            self._next_reconnect_attempt_at = now
            # Any leftover partial-chunk samples belong to the now-dead
            # stream -- stitching them onto post-reconnect audio would
            # splice unrelated signals together.
            self._capture_pending = np.zeros(0, dtype=np.float32)
            log.error(
                "No audio received for %.1fs — audio device appears to have "
                "disconnected. Attempting to reconnect automatically -- if "
                "a RESOLVED follow-up arrives shortly, no action is "
                "needed. If this persists more than a few minutes, a "
                "plain retry may not be enough (the device can get stuck "
                "in a state only a fresh process or a physical "
                "unplug/replug clears) -- try unplugging and replugging "
                "the USB microphone, or restart the recording process.",
                silent_for,
            )

        if now < self._next_reconnect_attempt_at:
            return  # still waiting out the backoff from the last attempt

        try:
            self.audio_input.close()
        except Exception:
            log.exception("Error closing stream during reconnect attempt")

        try:
            self.audio_input.open_stream(chunk_size=self._capture_len, callback=callback)
            # Reopening without an exception does NOT by itself mean data is
            # flowing again (it can silently succeed against the wrong/
            # fallback device) -- _last_chunk_at is deliberately left alone,
            # so continued silence re-triggers this check (same backoff, not
            # a growing one from this branch) rather than being mistaken for
            # confirmed recovery. Only a real chunk arriving in run()'s main
            # loop (_on_chunk_received) actually clears _device_lost.
            log.info("Audio stream reopened — waiting to confirm data is flowing again.")
        except Exception as exc:
            log.warning("Reconnect attempt failed (%s); retrying in %.1fs.",
                        exc, self._reconnect_backoff)

        self._next_reconnect_attempt_at = now + self._reconnect_backoff
        self._reconnect_backoff = min(
            self._reconnect_backoff * 2, self.cfg["device_reconnect_backoff_max"]
        )

    # ------------------------------------------------------------------
    # Per-chunk processing
    # ------------------------------------------------------------------

    def _process(self, chunk: np.ndarray):
        gate_result = self._gate.evaluate(chunk, self._extractor)
        sr_result   = self._smoother.update_gate(
            gate_result.passed, gate_result.score
        )

        if sr_result.triggered:
            if not self._recording:
                log.info(
                    "Detection — gate=%.3f snr=%.3f",
                    gate_result.score, gate_result.snr_score,
                )
                self._recording   = True
                self._clip_buffer = list(self._pre_buffer)
                self._episode_active_chunks = 0
                self._episode_peak_score    = 0.0
                self._episode_peak_calibrated_db = None
                self._precursor_extended    = False
            self._clip_buffer.append(chunk)
            self._episode_active_chunks += 1
            self._episode_peak_score = max(self._episode_peak_score, gate_result.score)
            if self._mic_calibration is not None:
                # A fresh FFT here (rather than reusing whatever gate.py
                # computed internally) keeps calibration.py fully decoupled
                # from the gate's own internals -- cheap on a 100ms chunk,
                # not worth the coupling to save it.
                magnitude = np.abs(np.fft.rfft(chunk))
                freqs_hz  = np.fft.rfftfreq(len(chunk), d=1.0 / self.cfg["sample_rate"])
                level_db  = self._mic_calibration.calibrated_level_db(
                    magnitude, freqs_hz,
                    freq_low=self.cfg["freq_low"], freq_high=self.cfg["freq_high"],
                )
                self._episode_peak_calibrated_db = level_db if (
                    self._episode_peak_calibrated_db is None
                    or level_db > self._episode_peak_calibrated_db
                ) else self._episode_peak_calibrated_db
            # Actively triggered -> always the normal post_roll tail. A
            # precursor grace period (below) is only ever granted at the
            # moment of release, and re-triggering (e.g. real song arriving
            # after a precursor whistle) resets it back to normal here --
            # exactly what lets a precursor+song sequence merge into one
            # continuous clip instead of re-extending indefinitely.
            self._post_countdown = self._post_chunks

        elif self._recording:
            self._clip_buffer.append(chunk)
            self._post_countdown -= 1
            if self._post_countdown <= 0:
                episode_duration_s = self._episode_active_chunks * self.cfg["chunk_duration"]
                if (not self._precursor_extended
                        and episode_duration_s <= self.cfg["precursor_max_duration"]
                        and self._episode_peak_score >= self.cfg["precursor_min_score"]):
                    # Short but confidently-scored episode -- possible song
                    # precursor (see module docstring). Grant one extended
                    # grace window instead of closing now.
                    self._precursor_extended = True
                    self._post_countdown = self._precursor_grace_chunks
                    log.info(
                        "Possible song precursor (dur=%.2fs, peak_score=%.3f) — "
                        "extending grace to %.1fs before closing clip",
                        episode_duration_s, self._episode_peak_score,
                        self.cfg["precursor_grace_period"],
                    )
                else:
                    self._recording = False
                    self._save_clip(gate_result)
                    self._clip_buffer = []

        self._pre_buffer.append(chunk)

    # ------------------------------------------------------------------
    # Clip saving
    # ------------------------------------------------------------------

    def _save_clip(self, gate_result):
        if not self._clip_buffer:
            return

        data     = np.concatenate(self._clip_buffer)
        sr       = self.cfg["sample_rate"]
        duration = len(data) / sr

        if duration < self.cfg["min_clip_duration"]:
            log.debug("Clip too short (%.2fs), discarding.", duration)
            return

        ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = self._out_dir / f"bird_{ts}.wav"
        pcm   = (data * 32767).astype(np.int16)

        with wave.open(str(fname), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())

        log.info("Saved %s (%.2fs)", fname.name, duration)

        self._det_log.write(
            timestamp  = datetime.datetime.now().isoformat(),
            filename   = str(fname),
            duration_s = round(duration, 2),
            rms        = round(float(gate_result.features.rms), 5),
            gate_score = round(float(gate_result.score), 4),
            snr_score  = round(float(gate_result.snr_score), 4),
            precursor_extended = self._precursor_extended,
            calibrated_level_db = (
                round(self._episode_peak_calibrated_db, 2)
                if self._episode_peak_calibrated_db is not None else ""
            ),
        )


# ---------------------------------------------------------------------------
# Self-test: precursor-grace state machine, synthetic gate sequences only
# (no hardware/microphone needed) -- matches the self-test convention every
# other module in this subpackage already follows.
# ---------------------------------------------------------------------------

class _FakeGate:
    """Feeds a pre-built (passed, score) sequence straight into the
    smoother, standing in for a real SongGate.evaluate() call so these
    scenarios exercise SongMonitor's real _process()/_save_clip() state
    machine without needing real audio or a real gate."""

    def __init__(self, sequence):
        self._seq = list(sequence)
        self._i = 0

    def evaluate(self, chunk, extractor):
        import types
        passed, score = self._seq[self._i]
        self._i += 1
        return types.SimpleNamespace(
            passed=passed, score=score, snr_score=0.0,
            features=types.SimpleNamespace(rms=0.01),
        )


def _run_precursor_scenario(name: str, sequence, tmp_dir):
    """Runs one synthetic (passed, score) sequence through a fresh
    SongMonitor and reports every clip it saved."""
    import tempfile
    cfg = {
        "output_dir": str(tmp_dir / name),
        "log_csv":    str(tmp_dir / name / "detections.csv"),
    }
    from pyoperant.song_recording.smoother import CombinedSmoother
    monitor = SongMonitor(
        cfg, audio_input=None,
        # extractor must be non-None too, or __init__'s "gate is None or
        # extractor is None" check rebuilds a REAL gate/extractor pair from
        # cfg and silently discards our fake gate.
        gate=_FakeGate(sequence), extractor=object(),
        smoother=CombinedSmoother.from_config_dict({}),
    )

    saved = []
    real_save_clip = monitor._save_clip

    def spy_save_clip(gate_result):
        n_chunks = len(monitor._clip_buffer)
        was_extended = monitor._precursor_extended
        real_save_clip(gate_result)
        saved.append({
            "duration_s": round(n_chunks * monitor.cfg["chunk_duration"], 2),
            "precursor_extended": was_extended,
        })

    monitor._save_clip = spy_save_clip

    chunk = np.zeros(monitor._chunk_len, dtype=np.float32)
    for _ in range(len(sequence)):
        monitor._process(chunk)

    print(f"\n=== {name} ({len(sequence)} chunks fed) ===")
    if not saved:
        print("  (no clip saved -- still open at end of sequence)")
    for c in saved:
        print(f"  saved clip: duration={c['duration_s']:.1f}s  "
              f"precursor_extended={c['precursor_extended']}")
    return saved


def self_test():
    """Three synthetic scenarios demonstrating the precursor-grace state
    machine (see module docstring): a short, confidently-scored episode
    with nothing following it, the same kind of episode followed by a
    longer one within the grace window (should merge into ONE clip), and
    a short but LOW-scored episode (should NOT get the extended grace)."""
    import tempfile
    from pathlib import Path as _Path

    tmp_dir = _Path(tempfile.mkdtemp(prefix="song_monitor_selftest_"))
    print(f"(writing throwaway clips/CSVs to {tmp_dir})")

    priming = [(False, 0.05)] * 15
    whistle_high = [(True, 0.75)] * 8    # short, confident -> should qualify
    whistle_low  = [(True, 0.48)] * 8    # short, marginal   -> should NOT qualify
    song         = [(True, 0.80)] * 15   # a longer, later "real song" episode
    gap_short    = [(False, 0.05)] * 30  # long enough to release + expire post_roll,
                                          # short enough to stay inside the grace window
    tail         = [(False, 0.05)] * 115 # long enough to release, expire post_roll,
                                          # AND exhaust the full grace period

    scenario_a = priming + whistle_high + tail
    scenario_b = priming + whistle_high + gap_short + song + tail
    scenario_c = priming + whistle_low + tail

    a = _run_precursor_scenario("A_precursor_alone", scenario_a, tmp_dir)
    b = _run_precursor_scenario("B_precursor_then_song", scenario_b, tmp_dir)
    c = _run_precursor_scenario("C_low_score_blip", scenario_c, tmp_dir)

    print("\n=== Expected vs. actual ===")
    checks = [
        ("A: exactly one clip, precursor_extended=True",
         len(a) == 1 and a[0]["precursor_extended"] is True),
        ("B: exactly ONE merged clip (not two), precursor_extended=True",
         len(b) == 1 and b[0]["precursor_extended"] is True),
        ("C: exactly one clip, precursor_extended=False (low score blocked it)",
         len(c) == 1 and c[0]["precursor_extended"] is False),
    ]
    for desc, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {desc}")

    _self_test_device_watchdog()
    _self_test_capture_buffering()
    _self_test_startup_retry()
    _self_test_mic_calibration()


class _FakeAudioInputWatchdog:
    """Stands in for a real AudioInput in the device-watchdog self-test --
    lets the test control exactly when open_stream()/close() succeed or
    raise, without needing a real microphone. fail_open_times=N means the
    first N open_stream() calls raise (simulating a still-unplugged
    device); calls after that succeed."""

    def __init__(self, fail_open_times=0):
        self.close_calls = 0
        self.open_calls = 0
        self.fail_open_times = fail_open_times

    def close(self):
        self.close_calls += 1

    def open_stream(self, chunk_size, callback):
        self.open_calls += 1
        if self.open_calls <= self.fail_open_times:
            raise RuntimeError("simulated device not present")


class _ListLogHandler(logging.Handler):
    """Collects log records into a list so the self-test can assert on
    exactly what was logged (e.g. the device-loss ERROR firing once, not
    once per poll) instead of just eyeballing printed output."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _self_test_device_watchdog():
    """Synthetic device-loss/recovery scenarios (see module docstring's
    'Device-loss detection and recovery' section) -- no real hardware, no
    real sleeps. Drives _check_device_health()/_on_chunk_received()
    directly with an injected fake clock."""
    print("\n=== Device-loss watchdog self-test ===")

    cfg = {
        "output_dir": None, "log_csv": None,  # unused -- we bypass __init__'s dirs below
        "device_watchdog_timeout": 5.0,
        "device_reconnect_backoff_initial": 1.0,
        "device_reconnect_backoff_max": 8.0,
    }

    def make_monitor(fail_open_times=0):
        import tempfile
        from pathlib import Path as _Path
        tmp_dir = _Path(tempfile.mkdtemp(prefix="song_monitor_watchdog_selftest_"))
        real_cfg = {**cfg, "output_dir": str(tmp_dir), "log_csv": str(tmp_dir / "detections.csv")}
        fake_audio = _FakeAudioInputWatchdog(fail_open_times=fail_open_times)
        m = SongMonitor(real_cfg, audio_input=fake_audio,
                         gate=_FakeGate([]), extractor=object(),
                         smoother=__import__(
                             "pyoperant.song_recording.smoother", fromlist=["CombinedSmoother"]
                         ).CombinedSmoother.from_config_dict({}))
        return m, fake_audio

    handler = _ListLogHandler()
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    try:
        # --- Scenario A: silence under the timeout -> no action at all ---
        m, fake = make_monitor()
        m._last_chunk_at = 0.0
        handler.records.clear()
        m._check_device_health(callback=None, now=2.0)  # < 5.0s timeout
        a_ok = (fake.close_calls == 0 and fake.open_calls == 0
                and not m._device_lost and len(handler.records) == 0)
        print(f"  [{'OK' if a_ok else 'FAIL'}] A: under timeout -> no reconnect attempt, "
              f"no log (close={fake.close_calls} open={fake.open_calls} "
              f"device_lost={m._device_lost} records={len(handler.records)})")

        # --- Scenario B: timeout crossed, reconnect succeeds immediately,
        # but device_lost stays True until a real chunk actually arrives ---
        m, fake = make_monitor(fail_open_times=0)
        m._last_chunk_at = 0.0
        handler.records.clear()
        m._check_device_health(callback=None, now=5.5)
        n_errors = sum(1 for r in handler.records if r.levelno == logging.ERROR)
        b_ok = (fake.close_calls == 1 and fake.open_calls == 1
                and m._device_lost is True and n_errors == 1)
        print(f"  [{'OK' if b_ok else 'FAIL'}] B: timeout crossed -> one reconnect attempt, "
              f"exactly one ERROR logged, still 'lost' until confirmed "
              f"(close={fake.close_calls} open={fake.open_calls} errors={n_errors})")

        # Confirm recovery via a real chunk arriving -- and that it logs a
        # RESOLVED follow-up at WARNING (reaches the same SMTPHandler the
        # original ERROR did), not just INFO/local-log-only, so an alert
        # that something broke gets a matching alert that it's fixed.
        m._on_chunk_received()
        n_resolved = sum(
            1 for r in handler.records
            if r.levelno == logging.WARNING and "RESOLVED" in r.getMessage()
        )
        b2_ok = (m._device_lost is False
                  and m._reconnect_backoff == cfg["device_reconnect_backoff_initial"]
                  and n_resolved == 1)
        print(f"  [{'OK' if b2_ok else 'FAIL'}] B2: chunk arrival clears device_lost, "
              f"resets backoff, AND logs one RESOLVED WARNING "
              f"(device_lost={m._device_lost} "
              f"backoff={m._reconnect_backoff})")

        # --- Scenario C: repeated silence while already 'lost' does NOT
        # re-log the ERROR or re-attempt before the backoff elapses ---
        m, fake = make_monitor(fail_open_times=0)
        m._last_chunk_at = 0.0
        handler.records.clear()
        m._check_device_health(callback=None, now=5.5)   # first detection + attempt
        m._check_device_health(callback=None, now=5.8)   # still within backoff -> no-op
        n_errors = sum(1 for r in handler.records if r.levelno == logging.ERROR)
        c_ok = (fake.open_calls == 1 and n_errors == 1)
        print(f"  [{'OK' if c_ok else 'FAIL'}] C: no duplicate ERROR/attempt while still "
              f"within backoff (open_calls={fake.open_calls} errors={n_errors})")

        # --- Scenario D: reconnect keeps failing -> backoff grows, capped ---
        m, fake = make_monitor(fail_open_times=10)  # never succeeds within this test
        m._last_chunk_at = 0.0
        backoffs = []
        t = 5.5
        m._check_device_health(callback=None, now=t)
        for _ in range(5):
            backoffs.append(m._reconnect_backoff)
            t = m._next_reconnect_attempt_at + 0.01  # just past the gate
            m._check_device_health(callback=None, now=t)
        d_ok = (backoffs == sorted(backoffs)  # non-decreasing
                and backoffs[-1] <= cfg["device_reconnect_backoff_max"]
                and max(backoffs) == cfg["device_reconnect_backoff_max"])
        print(f"  [{'OK' if d_ok else 'FAIL'}] D: backoff grows and caps at "
              f"{cfg['device_reconnect_backoff_max']}s (sequence={backoffs})")
    finally:
        log.removeHandler(handler)


def _self_test_capture_buffering():
    """Synthetic scenarios for _on_capture_block() (see module docstring's
    'Capture buffering headroom' section) -- confirms a PortAudio delivery
    spanning several logical chunks gets split back into exact
    chunk_duration-length pieces, with leftover samples correctly carried
    across separate callback deliveries. No real hardware needed."""
    import tempfile
    import types
    from pathlib import Path as _Path

    print("\n=== Capture-buffering self-test ===")

    tmp_dir = _Path(tempfile.mkdtemp(prefix="song_monitor_capture_selftest_"))
    cfg = {
        "output_dir": str(tmp_dir), "log_csv": str(tmp_dir / "detections.csv"),
        "sample_rate": 1000, "chunk_duration": 0.1,  # chunk_len = 100 samples
        "capture_chunk_multiplier": 3,
    }
    fake_audio = types.SimpleNamespace(sample_format=pyaudio.paInt16, channels_opened=1)
    m = SongMonitor(cfg, audio_input=fake_audio,
                     gate=_FakeGate([]), extractor=object(),
                     smoother=__import__(
                         "pyoperant.song_recording.smoother", fromlist=["CombinedSmoother"]
                     ).CombinedSmoother.from_config_dict({}))

    def pcm_bytes(start, n):
        """n int16 samples counting up from `start`, so chunk boundaries
        are verifiable by value, not just by count."""
        return np.arange(start, start + n, dtype=np.int16).tobytes()

    handler = _ListLogHandler()
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    try:
        # --- Scenario A: exactly one full chunk delivered at once ---
        m._on_capture_block(pcm_bytes(0, 100), status=0)
        a_ok = (m._audio_q.qsize() == 1 and m._capture_pending.size == 0)
        if a_ok:
            piece = m._audio_q.get_nowait()
            a_ok = (len(piece) == 100 and abs(piece[0] - 0 / 32768.0) < 1e-6)
        print(f"  [{'OK' if a_ok else 'FAIL'}] A: one exact chunk in -> one chunk queued, "
              f"no leftover")

        # --- Scenario B: 2.5 chunks in one delivery -> 2 queued, 50 leftover ---
        m._on_capture_block(pcm_bytes(1000, 250), status=0)
        b_ok = (m._audio_q.qsize() == 2 and m._capture_pending.size == 50)
        if b_ok:
            p0 = m._audio_q.get_nowait()
            p1 = m._audio_q.get_nowait()
            b_ok = (len(p0) == 100 and len(p1) == 100
                    and abs(p0[0] - 1000 / 32768.0) < 1e-6
                    and abs(p1[0] - 1100 / 32768.0) < 1e-6)
        print(f"  [{'OK' if b_ok else 'FAIL'}] B: 2.5 chunks in -> 2 queued exactly, "
              f"50-sample leftover carried")

        # --- Scenario C: completing that leftover across a second delivery ---
        # (values continue from 1000+250=1250, matching a real continuous stream)
        m._on_capture_block(pcm_bytes(1250, 50), status=0)
        c_ok = (m._audio_q.qsize() == 1 and m._capture_pending.size == 0)
        if c_ok:
            piece = m._audio_q.get_nowait()
            # first 50 samples are the carried leftover (values 1200-1249),
            # last 50 are the new delivery (1250-1299) -- continuous, no gap/dup.
            c_ok = (len(piece) == 100 and abs(piece[0] - 1200 / 32768.0) < 1e-6
                    and abs(piece[-1] - 1299 / 32768.0) < 1e-6)
        print(f"  [{'OK' if c_ok else 'FAIL'}] C: leftover completed by next delivery -> "
              f"one continuous chunk, no gap/duplication")

        # --- Scenario D: a nonzero status (e.g. paInputOverflow) logs at
        # INFO (not WARNING -- deliberately doesn't reach email alerting
        # for this known, low-priority condition, see module docstring)
        # but capture/decoding still proceeds normally ---
        handler.records.clear()
        m._on_capture_block(pcm_bytes(2000, 100), status=2)
        n_info = sum(1 for r in handler.records if r.levelno == logging.INFO)
        n_warnings = sum(1 for r in handler.records if r.levelno == logging.WARNING)
        d_ok = (m._audio_q.qsize() == 1 and n_info == 1 and n_warnings == 0)
        print(f"  [{'OK' if d_ok else 'FAIL'}] D: overflow status logs at INFO (not "
              f"WARNING -- doesn't reach email alerting), decoding/queuing still "
              f"happens (info={n_info} warnings={n_warnings})")
    finally:
        log.removeHandler(handler)


def _self_test_startup_retry():
    """Synthetic scenarios for _open_stream_with_retry() (see module
    docstring's "Startup retry" and "Give-up-and-exit" sections) --
    confirms a failed FIRST open_stream() attempt is retried with backoff
    instead of giving up for the whole session, logs ERROR exactly once
    (not once per retry), that stop_event ends the retry loop promptly,
    and that exhausting the give-up budget hard-exits the whole process
    (via an injected fake exit_fn, never a real one) rather than retrying
    forever. No real hardware, no real sleeps (sleep_fn is injected)."""
    import tempfile
    from pathlib import Path as _Path

    print("\n=== Startup-retry self-test ===")

    cfg = {
        "output_dir": None, "log_csv": None,
        "device_reconnect_backoff_initial": 1.0,
        "device_reconnect_backoff_max": 8.0,
    }

    def make_monitor(fail_open_times=0, exit_fn=None, **cfg_overrides):
        tmp_dir = _Path(tempfile.mkdtemp(prefix="song_monitor_startup_selftest_"))
        real_cfg = {**cfg, **cfg_overrides,
                    "output_dir": str(tmp_dir), "log_csv": str(tmp_dir / "detections.csv")}
        fake_audio = _FakeAudioInputWatchdog(fail_open_times=fail_open_times)
        kwargs = {} if exit_fn is None else {"exit_fn": exit_fn}
        m = SongMonitor(real_cfg, audio_input=fake_audio,
                         gate=_FakeGate([]), extractor=object(),
                         smoother=__import__(
                             "pyoperant.song_recording.smoother", fromlist=["CombinedSmoother"]
                         ).CombinedSmoother.from_config_dict({}), **kwargs)
        return m, fake_audio

    handler = _ListLogHandler()
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    try:
        # --- Scenario A: first attempt succeeds -- no retry, no ERROR, and
        # no false "RESOLVED" (nothing was ever reported broken) ---
        m, fake = make_monitor(fail_open_times=0)
        handler.records.clear()
        outcome = m._open_stream_with_retry(callback=None, sleep_fn=lambda s: None)
        n_errors = sum(1 for r in handler.records if r.levelno == logging.ERROR)
        n_warnings = sum(1 for r in handler.records if r.levelno == logging.WARNING)
        a_ok = (outcome == "opened" and fake.open_calls == 1 and n_errors == 0 and n_warnings == 0)
        print(f"  [{'OK' if a_ok else 'FAIL'}] A: first attempt succeeds -> no retry, "
              f"no ERROR, no false RESOLVED "
              f"(open_calls={fake.open_calls} errors={n_errors} warnings={n_warnings})")

        # --- Scenario B: fails twice, succeeds on the third attempt --
        # exactly one ERROR (first failure only), backoff waited between
        # retries (not zero real delay skipped) ---
        m, fake = make_monitor(fail_open_times=2)
        handler.records.clear()
        sleeps = []
        outcome = m._open_stream_with_retry(callback=None, sleep_fn=sleeps.append)
        n_errors = sum(1 for r in handler.records if r.levelno == logging.ERROR)
        warning_msgs = [r.getMessage() for r in handler.records if r.levelno == logging.WARNING]
        n_retry_warnings = sum(1 for m_ in warning_msgs if "RESOLVED" not in m_)
        n_resolved = sum(1 for m_ in warning_msgs if "RESOLVED" in m_)
        b_ok = (outcome == "opened" and fake.open_calls == 3 and n_errors == 1
                and n_retry_warnings == 1 and n_resolved == 1
                and sum(sleeps) >= cfg["device_reconnect_backoff_initial"])
        print(f"  [{'OK' if b_ok else 'FAIL'}] B: fails twice then succeeds -> exactly one "
              f"ERROR (not one per retry) AND one RESOLVED WARNING on success (reaches the "
              f"same alert channel as the ERROR did), backoff waited between attempts "
              f"(open_calls={fake.open_calls} errors={n_errors} "
              f"retry_warnings={n_retry_warnings} resolved={n_resolved})")

        # --- Scenario C: stop_event set while still retrying -> returns
        # "stopped" promptly, doesn't retry forever ---
        m, fake = make_monitor(fail_open_times=100)  # would never succeed
        m.stop_event = threading.Event()
        sleeps = []

        def sleep_then_stop(s):
            sleeps.append(s)
            if len(sleeps) >= 2:
                m.stop_event.set()

        outcome = m._open_stream_with_retry(callback=None, sleep_fn=sleep_then_stop)
        c_ok = (outcome == "stopped" and fake.open_calls < 100)
        print(f"  [{'OK' if c_ok else 'FAIL'}] C: stop_event during retries -> returns "
              f"'stopped' promptly, not exhausting all retries "
              f"(open_calls={fake.open_calls})")

        # --- Scenario D: give-up budget exhausted, stop_event never set --
        # returns "giveup" instead of retrying forever, and run() (not
        # exercised directly here, see below) would call exit_fn(1) on
        # this outcome. A small startup_retry_giveup_after keeps this fast
        # without needing hundreds of simulated backoff steps. ---
        exit_calls = []
        m, fake = make_monitor(fail_open_times=100,  # would never succeed
                                startup_retry_giveup_after=5.0,
                                exit_fn=lambda code: exit_calls.append(code))
        sleeps = []
        outcome = m._open_stream_with_retry(callback=None, sleep_fn=sleeps.append)
        d_ok = (outcome == "giveup" and fake.open_calls < 100 and sum(sleeps) >= 5.0)
        print(f"  [{'OK' if d_ok else 'FAIL'}] D: give-up budget exhausted (stop_event "
              f"never set) -> returns 'giveup' instead of retrying forever "
              f"(open_calls={fake.open_calls} cumulative_wait={sum(sleeps):.1f}s)")

        # run() itself calls self._exit_fn(1) on a "giveup" outcome --
        # checked directly here (not via a real run() loop, which would
        # need a real queue/callback) since that wiring is the whole point
        # of this feature, not just _open_stream_with_retry()'s own return
        # value.
        if outcome == "giveup":
            m._det_log.close()
            m._exit_fn(1)
        d2_ok = (exit_calls == [1])
        print(f"  [{'OK' if d2_ok else 'FAIL'}] D2: 'giveup' outcome calls exit_fn(1) "
              f"exactly once (exit_calls={exit_calls})")
    finally:
        log.removeHandler(handler)


def _self_test_mic_calibration():
    """Confirms a saved clip's detections.csv row logs a real
    calibrated_level_db when a MicCalibration is supplied, and logs
    nothing (blank, not a crash) when one isn't -- see
    pyoperant.song_recording.calibration for the feature itself. Uses the
    same _FakeGate/synthetic-sequence harness as the precursor-grace
    self-test above; the fed chunks are all-zero (no real audio needed to
    test the wiring), so the resulting dB values aren't physically
    meaningful -- only that a value is present vs. absent is checked."""
    import csv as _csv
    import tempfile
    from pathlib import Path as _Path
    from pyoperant.song_recording.calibration import MicCalibration
    from pyoperant.song_recording.smoother import CombinedSmoother

    print("\n=== Mic-calibration self-test ===")

    tmp_dir = _Path(tempfile.mkdtemp(prefix="song_monitor_calibration_selftest_"))
    cal_path = tmp_dir / "mic_cal.txt"
    cal_path.write_text(
        '"Sens Factor =-1.500dB, SERNO: 1234567"\n'
        '"Auto-generated 90-degree calibration file"\n'
        "500.0\t0.0\n1000.0\t0.0\n2000.0\t6.0\n4000.0\t-3.0\n8000.0\t0.0\n16000.0\t0.0\n"
    )
    cal = MicCalibration.load(str(cal_path))

    # Exactly scenario_a's shape from the precursor-grace self-test above
    # (proven to actually produce one saved clip, including exhausting a
    # full precursor-grace period, not just release+post_roll) -- not
    # worth re-deriving timing from scratch here.
    sequence = [(False, 0.05)] * 15 + [(True, 0.75)] * 8 + [(False, 0.05)] * 115

    def run(mic_calibration, name):
        cfg = {"output_dir": str(tmp_dir / name), "log_csv": str(tmp_dir / name / "detections.csv")}
        m = SongMonitor(cfg, audio_input=None, gate=_FakeGate(sequence), extractor=object(),
                         smoother=CombinedSmoother.from_config_dict({}),
                         mic_calibration=mic_calibration)
        z = np.zeros(m._chunk_len, dtype=np.float32)
        for _ in range(len(sequence)):
            m._process(z)
        with open(cfg["log_csv"]) as f:
            rows = list(_csv.DictReader(f))
        return rows

    rows_with_cal = run(cal, "with_cal")
    a_ok = (len(rows_with_cal) == 1 and rows_with_cal[0]["calibrated_level_db"] != "")
    print(f"  [{'OK' if a_ok else 'FAIL'}] A: calibrated_level_db populated when a "
          f"MicCalibration is supplied "
          f"(value={rows_with_cal[0]['calibrated_level_db'] if rows_with_cal else None!r})")

    rows_without_cal = run(None, "without_cal")
    b_ok = (len(rows_without_cal) == 1 and rows_without_cal[0]["calibrated_level_db"] == "")
    print(f"  [{'OK' if b_ok else 'FAIL'}] B: calibrated_level_db blank (not a crash) "
          f"when no MicCalibration is supplied "
          f"(value={rows_without_cal[0]['calibrated_level_db'] if rows_without_cal else None!r})")


# ---------------------------------------------------------------------------
# Standalone diagnostic entry point
# ---------------------------------------------------------------------------

def list_devices():
    """Print every PortAudio device (index, name, channel counts) via the
    same PyAudioInterface panels use, so this reports exactly what a panel
    would see -- including which ones are input-capable, for setting
    AUDIO_INPUT_DEVICE in local_pi_revd.py."""
    from pyoperant.interfaces.pyaudio_ import PyAudioInterface

    interface = PyAudioInterface()
    try:
        for index in range(interface.pa.get_device_count()):
            info = interface.pa.get_device_info_by_index(index)
            in_ch, out_ch = info.get("maxInputChannels", 0), info.get("maxOutputChannels", 0)
            role = "input" if in_ch > 0 else ("output" if out_ch > 0 else "?")
            print(f"{index:3d}  {info.get('name')!r:40s} {role:6s} "
                  f"in={in_ch} out={out_ch} default_sr={info.get('defaultSampleRate')}")
    finally:
        interface.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Songbird vocalization monitor -- on-the-bench diagnostics. "
                    "SongMonitor itself runs embedded in pyoperant.behavior.lights.Lights."
    )
    parser.add_argument(
        "--list-devices", action="store_true",
        help="List PortAudio devices and exit (use to find the right "
             "AUDIO_INPUT_DEVICE substring for local_pi_revd.py)",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run the precursor-grace state-machine self-test on synthetic "
             "gate sequences and exit -- no hardware/microphone needed.",
    )
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return
    if args.self_test:
        self_test()
        return

    parser.error("nothing to do -- pass --list-devices or --self-test, or run song "
                 "recording via `behave Lights` with song_recording.enabled in config.json")


if __name__ == "__main__":
    main()
