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
itself: requesting a bigger block per PortAudio callback gives ALSA more
periods/more total buffered audio in flight, at the cost of a larger chunk
of raw bytes delivered per callback. `capture_chunk_multiplier` (default 3)
controls how many logical `chunk_duration` chunks are requested per
callback (e.g. 300ms of PortAudio buffering instead of 100ms) --
`_on_capture_block()` immediately splits whatever arrives back into exact
`chunk_duration`-length pieces (carrying any leftover samples across
callbacks) before queuing, so the gate/smoother/precursor-grace state
machine downstream -- all of which assume every queued chunk is exactly
one `chunk_duration` long -- needs no changes. Trade-off: up to roughly
`(capture_chunk_multiplier - 1) * chunk_duration` of added worst-case
latency before the last sub-chunk in a block reaches the gate (~200ms at
the default), negligible against `pre_roll`/`precursor_grace_period`.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import logging
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
    # Capture buffering headroom -- see module docstring. Requests
    # capture_chunk_multiplier logical chunks per PortAudio callback
    # (more ALSA-side buffering headroom) and splits them back into exact
    # chunk_duration pieces before anything downstream sees them.
    "capture_chunk_multiplier": 3,
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
    "output_dir":        "recordings",
    "log_csv":           "detections.csv",
}


# ---------------------------------------------------------------------------
# Detection log (CSV)
# ---------------------------------------------------------------------------

class DetectionLog:
    FIELDS = ["timestamp", "filename", "duration_s", "rms",
              "gate_score", "snr_score", "precursor_extended"]

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
    """

    def __init__(
        self,
        cfg:         dict,
        audio_input,
        gate=None,
        extractor=None,
        smoother=None,
        stop_event: Optional[threading.Event] = None,
    ):
        self.cfg         = {**DEFAULT_CONFIG, **cfg}
        self.audio_input = audio_input
        self.stop_event  = stop_event
        self._gate       = gate
        self._extractor  = extractor
        self._smoother   = smoother

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
            log.warning("Audio status: %s", status)
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

        self.audio_input.open_stream(chunk_size=self._capture_len, callback=_audio_callback)
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
            log.info("Audio device recovered — resuming normal monitoring.")
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
                "disconnected. Attempting to reconnect.", silent_for,
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
                self._precursor_extended    = False
            self._clip_buffer.append(chunk)
            self._episode_active_chunks += 1
            self._episode_peak_score = max(self._episode_peak_score, gate_result.score)
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

        # Confirm recovery via a real chunk arriving.
        m._on_chunk_received()
        b2_ok = (m._device_lost is False
                  and m._reconnect_backoff == cfg["device_reconnect_backoff_initial"])
        print(f"  [{'OK' if b2_ok else 'FAIL'}] B2: chunk arrival clears device_lost "
              f"and resets backoff (device_lost={m._device_lost} "
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

        # --- Scenario D: a nonzero status (e.g. paInputOverflow) logs a
        # warning but capture/decoding still proceeds normally ---
        handler.records.clear()
        m._on_capture_block(pcm_bytes(2000, 100), status=2)
        n_warnings = sum(1 for r in handler.records if r.levelno == logging.WARNING)
        d_ok = (m._audio_q.qsize() == 1 and n_warnings == 1)
        print(f"  [{'OK' if d_ok else 'FAIL'}] D: overflow status logs one WARNING, "
              f"decoding/queuing still happens (warnings={n_warnings})")
    finally:
        log.removeHandler(handler)


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
