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
    "output_dir":        "recordings",
    "log_csv":           "detections.csv",
}


# ---------------------------------------------------------------------------
# Detection log (CSV)
# ---------------------------------------------------------------------------

class DetectionLog:
    FIELDS = ["timestamp", "filename", "duration_s", "rms",
              "gate_score", "snr_score"]

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

        if self._gate is None or self._extractor is None:
            self._build_pipeline()
        if self._smoother is None:
            self._build_smoother()

        sr  = self.cfg["sample_rate"]
        dur = self.cfg["chunk_duration"]
        self._chunk_len      = int(sr * dur)
        self._pre_buffer     = collections.deque(maxlen=int(self.cfg["pre_roll"] / dur))
        self._post_chunks    = int(self.cfg["post_roll"] / dur)
        self._recording      = False
        self._post_countdown = 0
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
            self._clip_buffer.append(chunk)
            self._post_countdown = self._post_chunks

        elif self._recording:
            self._clip_buffer.append(chunk)
            self._post_countdown -= 1
            if self._post_countdown <= 0:
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
        )


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
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    parser.error("nothing to do -- pass --list-devices, or run song recording "
                 "via `behave Lights` with song_recording.enabled in config.json")


if __name__ == "__main__":
    main()
