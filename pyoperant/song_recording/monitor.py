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
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import logging
import queue
import threading
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
    "freq_low":          1000,
    "freq_high":         10000,
    "pre_roll":          1.0,
    "post_roll":         2.0,
    "min_clip_duration": 0.5,
    # Song-precursor grace period -- see module docstring.
    "precursor_max_duration": 3.0,   # episode must be no longer than this to qualify
    "precursor_min_score":    0.55,  # ...and confidently scored (base gate.threshold is 0.45)
    "precursor_grace_period": 8.0,   # extended hangover granted instead of post_roll
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

    def run(self):
        """Open the audio stream and process chunks until stop_event is set."""

        def _audio_callback(in_data, frame_count, time_info, status):
            if status:
                log.warning("Audio status: %s", status)
            try:
                chunk = decode_pcm(in_data, self.audio_input.sample_format,
                                    self.audio_input.channels_opened)
                self._audio_q.put_nowait(chunk)
            except queue.Full:
                pass
            except Exception:
                log.exception("Error decoding audio callback data")
            return (None, pyaudio.paContinue)

        log.info(
            "Monitor starting (sr=%d, chunk=%.0fms)",
            self.cfg["sample_rate"], self.cfg["chunk_duration"] * 1000,
        )

        self.audio_input.open_stream(chunk_size=self._chunk_len, callback=_audio_callback)
        try:
            while not self._should_stop():
                try:
                    chunk = self._audio_q.get(timeout=0.5)
                    self._process(chunk)
                except queue.Empty:
                    pass
        except KeyboardInterrupt:
            log.info("Monitor stopped by KeyboardInterrupt.")
        finally:
            self.audio_input.close()
            self._det_log.close()
            log.info("Monitor stopped. Recordings in %s", self._out_dir)

    def _should_stop(self) -> bool:
        return self.stop_event is not None and self.stop_event.is_set()

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
