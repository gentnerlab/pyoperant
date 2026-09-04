"""
noise_model.py — Per-chamber adaptive spectral noise floor.

Overview
--------
This module learns what silence sounds like in a specific sound-isolation
chamber and uses that knowledge to replace the fixed RMS threshold in the
detection gate.

Two-phase design
----------------
Calibration (lights-off window, ~30–60 s)
    Record ambient audio while the bird is definitely not singing.
    For each FFT bin in the vocalization band, compute:
        noise_floor_db  = median log-power across all calibration chunks
        noise_mad_db    = median absolute deviation (spread / reliability)
        threshold_db    = noise_floor_db + k * noise_mad_db
    Save the model to disk.

Drift correction (next lights-off window)
    Load the saved model, record a short update pass (~10 s), and apply
    a slow exponential update to each bin's floor estimate.  k and other
    parameters are preserved from the original calibration.

Runtime (during a session)
    Load the model once at startup.  On every audio chunk, compute the
    band SNR score: the fraction of vocalization-band bins where the
    current signal exceeds the per-bin threshold_db.  This replaces the
    raw RMS gate in gate.py.

pyoperant integration
---------------------
calibrate()/update_drift() record via a pyoperant.hwio.AudioInput --
typically the panel's own microphone (panel.microphone), so calibration
shares the same PortAudio context pyoperant.behavior.lights.Lights already
opened for that panel rather than a second, standalone one:

    from pyoperant.song_recording.noise_model import calibrate, NoiseModel

    # At lights-off (start of dark period)
    model = calibrate(audio_input=panel.microphone, duration_s=45)
    model.save("noise_model.npz")

    # At lights-on (start of light period) — load and hand to the gate
    model = NoiseModel.load("noise_model.npz")

    # After many sessions — periodic drift correction (optional)
    model = NoiseModel.load("noise_model.npz")
    model = update_drift(model, audio_input=panel.microphone, duration_s=10)
    model.save("noise_model.npz")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pyoperant.song_recording._pcm import decode_pcm

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Small value added before log to avoid log(0)
_EPS = 1e-12

# Minimum number of calibration chunks required for a reliable model.
# At 100 ms chunks this is 5 seconds minimum.
_MIN_CHUNKS = 50


# ---------------------------------------------------------------------------
# NoiseModel — the learned per-bin noise floor
# ---------------------------------------------------------------------------

@dataclass
class NoiseModel:
    """
    Learned spectral noise floor for one chamber.

    Attributes
    ----------
    sample_rate     : int    Audio sample rate used during calibration.
    n_fft           : int    FFT size used during calibration.
    freq_low        : int    Lower edge of vocalization band (Hz).
    freq_high       : int    Upper edge of vocalization band (Hz).
    freqs           : ndarray  Frequency of each FFT bin (Hz).
    band_mask       : ndarray  Boolean mask for vocalization band bins.
    noise_floor_db  : ndarray  Per-bin median log-power (dB re 1.0).
    noise_mad_db    : ndarray  Per-bin median absolute deviation (dB).
    threshold_db    : ndarray  Per-bin detection threshold (dB).
    sensitivity_k   : float  Multiplier used to set threshold_db from MAD.
    n_chunks        : int    Number of chunks used for calibration.
    calibrated_at   : float  Unix timestamp of calibration.
    device_id       : str    Identifier of the recording device/chamber.
    """

    sample_rate:    int
    n_fft:          int
    freq_low:       int
    freq_high:      int
    freqs:          np.ndarray
    band_mask:      np.ndarray
    noise_floor_db: np.ndarray   # shape: (n_fft // 2 + 1,)
    noise_mad_db:   np.ndarray   # shape: (n_fft // 2 + 1,)
    threshold_db:   np.ndarray   # shape: (n_fft // 2 + 1,)
    sensitivity_k:  float  = 4.0
    n_chunks:       int    = 0
    calibrated_at:  float  = 0.0
    device_id:      str    = ""

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Save model to a compressed .npz file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            sample_rate    = np.array(self.sample_rate),
            n_fft          = np.array(self.n_fft),
            freq_low       = np.array(self.freq_low),
            freq_high      = np.array(self.freq_high),
            freqs          = self.freqs,
            band_mask      = self.band_mask,
            noise_floor_db = self.noise_floor_db,
            noise_mad_db   = self.noise_mad_db,
            threshold_db   = self.threshold_db,
            sensitivity_k  = np.array(self.sensitivity_k),
            n_chunks       = np.array(self.n_chunks),
            calibrated_at  = np.array(self.calibrated_at),
            device_id      = np.array(self.device_id),
        )
        log.info("Noise model saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "NoiseModel":
        """Load a previously saved noise model."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Noise model not found: {path}")
        d = np.load(path, allow_pickle=False)
        model = cls(
            sample_rate    = int(d["sample_rate"]),
            n_fft          = int(d["n_fft"]),
            freq_low       = int(d["freq_low"]),
            freq_high      = int(d["freq_high"]),
            freqs          = d["freqs"],
            band_mask      = d["band_mask"].astype(bool),
            noise_floor_db = d["noise_floor_db"],
            noise_mad_db   = d["noise_mad_db"],
            threshold_db   = d["threshold_db"],
            sensitivity_k  = float(d["sensitivity_k"]),
            n_chunks       = int(d["n_chunks"]),
            calibrated_at  = float(d["calibrated_at"]),
            device_id      = str(d["device_id"]),
        )
        age_h = (time.time() - model.calibrated_at) / 3600
        log.info(
            "Noise model loaded from %s "
            "(calibrated %.1f h ago, %d chunks, device=%s)",
            path, age_h, model.n_chunks, model.device_id,
        )
        return model

    # ------------------------------------------------------------------
    # Runtime scoring
    # ------------------------------------------------------------------

    def band_snr_score(self, magnitude: np.ndarray) -> float:
        """
        Compute the band SNR score for one audio chunk.

        For each bin in the vocalization band, check whether the current
        signal power exceeds the learned per-bin threshold.  Return the
        fraction of band bins that exceed their threshold.

        Parameters
        ----------
        magnitude : np.ndarray
            rfft magnitude spectrum of the chunk, length n_fft // 2 + 1.

        Returns
        -------
        float in [0, 1].
            0   = all band bins below noise floor (silence / known noise)
            1   = all band bins above threshold (strong in-band signal)

        Typical values
        --------------
            > 0.3   likely birdsong  (many bins well above floor)
            < 0.1   likely silence or cage noise

        The threshold for using this score as a gate pass/fail is set in
        NoiseModelGateConfig.snr_score_threshold.
        """
        signal_db = 20.0 * np.log10(magnitude[self.band_mask] + _EPS)
        above     = signal_db > self.threshold_db[self.band_mask]
        return float(above.mean())

    def per_bin_snr_db(self, magnitude: np.ndarray) -> np.ndarray:
        """
        Return per-bin SNR (signal - noise_floor) in dB for the full spectrum.
        Useful for visualisation and debugging.
        """
        signal_db = 20.0 * np.log10(magnitude + _EPS)
        return signal_db - self.noise_floor_db

    def summary(self) -> str:
        """Human-readable summary of the model."""
        band_floor_mean = self.noise_floor_db[self.band_mask].mean()
        band_mad_mean   = self.noise_mad_db[self.band_mask].mean()
        band_thr_mean   = self.threshold_db[self.band_mask].mean()
        return (
            f"NoiseModel(device={self.device_id!r}, "
            f"n_chunks={self.n_chunks}, "
            f"band_floor={band_floor_mean:.1f} dB, "
            f"band_mad={band_mad_mean:.1f} dB, "
            f"band_threshold={band_thr_mean:.1f} dB, "
            f"k={self.sensitivity_k})"
        )


# ---------------------------------------------------------------------------
# Capture helper — shared by calibrate() and update_drift()
# ---------------------------------------------------------------------------

def _record_chunks(audio_input, duration_s: float, chunk_len: int,
                    progress: bool, label: str) -> list[np.ndarray]:
    """Blocking-record duration_s seconds via audio_input (a
    pyoperant.hwio.AudioInput), decoded to mono float32 chunks of
    chunk_len samples each. Always closes the stream when done, even on
    error, so a failed/aborted calibration doesn't leave the mic open."""
    n_expected = int(duration_s / (chunk_len / audio_input.sample_rate))
    audio_input.open_stream(chunk_size=chunk_len)
    try:
        chunks: list[np.ndarray] = []
        start = time.time()
        while time.time() - start < duration_s:
            raw = audio_input.read(chunk_len)
            chunks.append(decode_pcm(raw, audio_input.sample_format,
                                      audio_input.channels_opened))
            if progress and len(chunks) % 10 == 0:
                elapsed = time.time() - start
                pct = min(100, int(100 * elapsed / duration_s))
                print(f"\r  {pct:3d}% [{len(chunks):4d} chunks]", end="", flush=True)
        if progress:
            print(f"\r  100% [{len(chunks):4d} chunks] — done.     ")
        return chunks
    finally:
        audio_input.close()


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def calibrate(
    audio_input,
    duration_s:    float = 45.0,
    chunk_dur:     float = 0.1,
    freq_low:      int   = 1000,
    freq_high:     int   = 10000,
    sensitivity_k: float = 3.0,
    device_id:     str   = "",
    progress:      bool  = True,
) -> NoiseModel:
    """
    Record ambient audio and build a per-bin spectral noise floor model.

    This function should be called during lights-off when the bird is
    not singing.  It records `duration_s` seconds of audio via audio_input
    (a pyoperant.hwio.AudioInput -- typically panel.microphone), computes
    the magnitude spectrum of each 100 ms chunk, and estimates the noise
    floor at every FFT bin as:

        noise_floor_db[bin] = median(power_db[bin] over all chunks)
        noise_mad_db[bin]   = median(|power_db[bin] - floor[bin]|)
        threshold_db[bin]   = noise_floor_db[bin] + k * noise_mad_db[bin]

    Using median and MAD rather than mean and std makes the estimate robust
    to occasional transients during calibration (wing flaps, cage hops).

    Parameters
    ----------
    audio_input   : pyoperant.hwio.AudioInput to record from.
    duration_s    : How many seconds of ambient audio to record.
    chunk_dur     : Analysis window size in seconds.
    freq_low      : Lower edge of vocalization band (Hz).
    freq_high     : Upper edge of vocalization band (Hz).
    sensitivity_k : Threshold = floor + k * MAD.  Higher = less sensitive
                    (fewer false positives); lower = more sensitive.
    device_id     : Human-readable identifier for this chamber/device.
    progress      : Print progress dots to stdout during recording.

    Returns
    -------
    NoiseModel ready for use or saving.

    Raises
    ------
    RuntimeError  if fewer than _MIN_CHUNKS were collected.
    """
    sample_rate = audio_input.sample_rate
    chunk_len   = int(sample_rate * chunk_dur)
    n_fft       = chunk_len
    freqs       = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    band_mask   = (freqs >= freq_low) & (freqs <= freq_high)

    log.info(
        "Calibration starting: %.0f s, sr=%d, k=%.1f, id=%r",
        duration_s, sample_rate, sensitivity_k, device_id,
    )
    if progress:
        print(
            f"Calibrating noise model for {device_id!r}...\n"
            f"Recording {duration_s:.0f} s of ambient audio. "
            f"Ensure bird is not vocalising.",
            flush=True,
        )

    chunks = _record_chunks(audio_input, duration_s, chunk_len, progress,
                             label="calibration")

    if len(chunks) < _MIN_CHUNKS:
        raise RuntimeError(
            f"Only {len(chunks)} chunks collected; need at least {_MIN_CHUNKS}. "
            f"Is the audio device working?"
        )

    log.info("Collected %d calibration chunks", len(chunks))
    return _build_model(
        chunks        = chunks,
        freqs         = freqs,
        band_mask     = band_mask,
        sample_rate   = sample_rate,
        n_fft         = n_fft,
        freq_low      = freq_low,
        freq_high     = freq_high,
        sensitivity_k = sensitivity_k,
        device_id     = device_id,
    )


def calibrate_from_config(audio_input, cfg: dict, device_id: str = "") -> NoiseModel:
    """
    Convenience wrapper that reads calibration parameters from a
    song_recording config dict (see pyoperant.behavior.lights).

    Expected config structure (all optional, fall back to defaults):

        noise_model:
          calibration_duration_s: 45
          sensitivity_k: 3.0
          model_path: noise_model.npz
    """
    nc = cfg.get("noise_model", {})
    return calibrate(
        audio_input   = audio_input,
        duration_s    = nc.get("calibration_duration_s", 45.0),
        chunk_dur     = cfg.get("chunk_duration", 0.1),
        freq_low      = cfg.get("freq_low",  1000),
        freq_high     = cfg.get("freq_high", 10000),
        sensitivity_k = nc.get("sensitivity_k", 4.0),
        device_id     = device_id or cfg.get("device_id", ""),
    )


# ---------------------------------------------------------------------------
# Drift correction (optional — called at next lights-off window)
# ---------------------------------------------------------------------------

def update_drift(
    model:       NoiseModel,
    audio_input,
    duration_s:  float = 10.0,
    alpha:       float = 0.2,
    progress:    bool  = True,
) -> NoiseModel:
    """
    Apply a slow exponential update to an existing noise model using a
    short lights-off recording.

    The update rule for each bin is:

        noise_floor_db_new = (1 - alpha) * floor_old + alpha * floor_new

    where floor_new is estimated from the current short recording.
    alpha = 0.2 means the new recording contributes 20% of the final model.
    This prevents a single unusual lights-off window from corrupting the model.

    Parameters
    ----------
    model      : Existing NoiseModel (loaded from disk).
    audio_input : pyoperant.hwio.AudioInput to record from.
    duration_s : How many seconds to record for the update.
    alpha      : EMA weight for the new measurement (0 = ignore, 1 = replace).
    progress   : Print progress to stdout.

    Returns
    -------
    Updated NoiseModel (same object mutated in place, also returned).
    """
    chunk_len = int(model.sample_rate * 0.1)   # reuse model's chunk size

    log.info("Drift correction: %.0f s, alpha=%.2f", duration_s, alpha)
    if progress:
        print(f"Drift correction for {model.device_id!r} ({duration_s:.0f} s)...", flush=True)

    chunks = _record_chunks(audio_input, duration_s, chunk_len, progress,
                             label="drift correction")

    if not chunks:
        log.warning("No chunks collected during drift correction; skipping.")
        return model

    # Build a fresh floor from the short recording
    fresh = _build_model(
        chunks        = chunks,
        freqs         = model.freqs,
        band_mask     = model.band_mask,
        sample_rate   = model.sample_rate,
        n_fft         = model.n_fft,
        freq_low      = model.freq_low,
        freq_high     = model.freq_high,
        sensitivity_k = model.sensitivity_k,
        device_id     = model.device_id,
    )

    # Exponential blend
    model.noise_floor_db = (
        (1 - alpha) * model.noise_floor_db + alpha * fresh.noise_floor_db
    )
    model.noise_mad_db = (
        (1 - alpha) * model.noise_mad_db + alpha * fresh.noise_mad_db
    )
    model.threshold_db = (
        model.noise_floor_db + model.sensitivity_k * model.noise_mad_db
    )
    model.n_chunks     += len(chunks)
    model.calibrated_at = time.time()

    log.info("Drift correction applied (alpha=%.2f, %d new chunks)", alpha, len(chunks))
    return model


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_model(
    chunks:        list[np.ndarray],
    freqs:         np.ndarray,
    band_mask:     np.ndarray,
    sample_rate:   int,
    n_fft:         int,
    freq_low:      int,
    freq_high:     int,
    sensitivity_k: float,
    device_id:     str,
) -> NoiseModel:
    """
    Build a NoiseModel from a list of audio chunks.

    Internal function — shared by calibrate() and update_drift().
    """
    # Compute log-power spectrum for every chunk
    # shape: (n_chunks, n_fft // 2 + 1)
    spectra_db = np.array([
        20.0 * np.log10(np.abs(np.fft.rfft(c, n=n_fft)) + _EPS)
        for c in chunks
    ], dtype=np.float32)

    # Per-bin statistics (axis=0 = across chunks)
    noise_floor_db = np.median(spectra_db, axis=0)
    noise_mad_db   = np.median(np.abs(spectra_db - noise_floor_db), axis=0)
    threshold_db   = noise_floor_db + sensitivity_k * noise_mad_db

    # Diagnostic: report the band floor and expected threshold
    band_floor_mean = float(noise_floor_db[band_mask].mean())
    band_thr_mean   = float(threshold_db[band_mask].mean())
    log.info(
        "Noise model built: %d chunks, "
        "band floor=%.1f dB, threshold=%.1f dB (k=%.1f)",
        len(chunks), band_floor_mean, band_thr_mean, sensitivity_k,
    )

    return NoiseModel(
        sample_rate    = sample_rate,
        n_fft          = n_fft,
        freq_low       = freq_low,
        freq_high      = freq_high,
        freqs          = freqs,
        band_mask      = band_mask,
        noise_floor_db = noise_floor_db,
        noise_mad_db   = noise_mad_db,
        threshold_db   = threshold_db,
        sensitivity_k  = sensitivity_k,
        n_chunks       = len(chunks),
        calibrated_at  = time.time(),
        device_id      = device_id,
    )


# ---------------------------------------------------------------------------
# NoiseModelGateConfig — how the model plugs into SongGate
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dc

@_dc
class NoiseModelGateConfig:
    """
    Configuration for using a NoiseModel inside the SongGate.

    snr_score_threshold
        The band_snr_score must exceed this to pass the noise-model gate.
        0.20 means at least 20% of vocalization-band bins must be above
        their learned threshold.

    fallback_rms_floor
        If no noise model is available (first run, model file missing),
        fall back to this fixed RMS threshold.  Set to the same value as
        gate: rms_floor in the song_recording config.

    model_path
        Where to look for the saved noise model.
    """
    snr_score_threshold: float = 0.001
    fallback_rms_floor:  float = 0.003
    model_path:          str   = "noise_model.npz"

    @classmethod
    def from_config_dict(cls, cfg: dict) -> "NoiseModelGateConfig":
        nc = cfg.get("noise_model", {})
        return cls(
            snr_score_threshold = nc.get("snr_score_threshold", cls.snr_score_threshold),
            fallback_rms_floor  = nc.get("fallback_rms_floor",  cls.fallback_rms_floor),
            model_path          = nc.get("model_path",          cls.model_path),
        )


# ---------------------------------------------------------------------------
# Self-test / diagnostics (run directly: python -m pyoperant.song_recording.noise_model)
# Synthetic signals only -- no microphone/hardware required.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    print("=== NoiseModel offline diagnostics (no microphone required) ===\n")

    sr        = 44100
    chunk_dur = 0.1
    chunk_len = int(sr * chunk_dur)
    n_fft     = chunk_len
    freq_low, freq_high = 1000, 10000
    t = np.linspace(0, chunk_dur, chunk_len, endpoint=False)
    rng = np.random.default_rng(42)

    # Simulate calibration: 60 chunks of realistic chamber noise
    # (band-limited noise with occasional transients)
    sim_chunks = []
    for i in range(60):
        base = 0.005 * rng.standard_normal(chunk_len).astype(np.float32)
        # Occasional transients (cage noise)
        if i % 15 == 0:
            pos = rng.integers(chunk_len // 4, 3 * chunk_len // 4)
            base[pos] += 0.08
        sim_chunks.append(base)

    freqs     = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    band_mask = (freqs >= freq_low) & (freqs <= freq_high)

    model = _build_model(
        chunks        = sim_chunks,
        freqs         = freqs,
        band_mask     = band_mask,
        sample_rate   = sr,
        n_fft         = n_fft,
        freq_low      = freq_low,
        freq_high      = freq_high,
        sensitivity_k = 4.0,
        device_id     = "sim-chamber-01",
    )
    print(f"Built model: {model.summary()}\n")

    # Test scoring on different signal types
    test_cases = {
        "Silence":                np.zeros(chunk_len, dtype=np.float32),
        "Noise-level signal":     (0.005 * rng.standard_normal(chunk_len)).astype(np.float32),
        "Pure 3 kHz tone (weak)": (0.008 * np.sin(2*np.pi*3000*t)).astype(np.float32),
        "Pure 3 kHz tone (med)":  (0.03  * np.sin(2*np.pi*3000*t)).astype(np.float32),
        "Harmonic 2 kHz (med)":   (
            0.025 * np.sin(2*np.pi*2000*t) +
            0.015 * np.sin(2*np.pi*4000*t) +
            0.010 * np.sin(2*np.pi*6000*t)
        ).astype(np.float32),
        "FM sweep 1-8 kHz":       (0.025 * np.sin(2*np.pi*np.cumsum(
                                     np.linspace(1000,8000,chunk_len))/sr)).astype(np.float32),
        "Impulse (cage wire)":    (lambda a: (a.__setitem__(chunk_len//4, 0.3) or a)
                                  )(np.zeros(chunk_len, np.float32)),
    }

    print(f"{'Signal':<30}  {'SNR score':>9}  {'Gate pass?':>10}  (threshold=0.001)")
    print("-" * 60)
    for name, chunk in test_cases.items():
        mag   = np.abs(np.fft.rfft(chunk, n=n_fft))
        score = model.band_snr_score(mag)
        passed = score >= 0.20
        print(f"  {name:<28}  {score:9.3f}  {'PASS' if passed else 'fail':>10}")

    # Test save / load round-trip
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as tmp:
        tmp_path = tmp.name
    model.save(tmp_path)
    model2 = NoiseModel.load(tmp_path)
    os.unlink(tmp_path)
    assert np.allclose(model.threshold_db, model2.threshold_db), "Save/load mismatch!"
    print(f"\nSave/load round-trip: OK")
    print(f"\nExpected: silence/noise fail; tones/sweeps above noise level PASS")
