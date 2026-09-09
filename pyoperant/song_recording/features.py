"""
features.py — Signal-processing feature extraction for birdsong detection.

All features operate on a single mono float32 numpy array (one audio chunk).
They are designed to be fast enough to run on every 100 ms chunk on a Pi 3B+.

Features computed
-----------------
rms                 Overall loudness. Near-zero = silence.
spectral_flatness   0 = pure tone (birdsong), 1 = white noise (cage rattle).
                    Computed as geometric_mean(|X|) / arithmetic_mean(|X|)
                    restricted to the bird-vocalization band.
onset_sharpness     How impulsive the sound is. High = sudden bang (cage wire);
                    low = shaped syllable envelope (song). Measured as the
                    peak-to-mean ratio of the chunk's amplitude envelope.
harmonic_ratio      Fraction of energy that aligns with harmonics of the
                    strongest detected fundamental. High = tonal/harmonic
                    (birdsong); low = aperiodic noise.
band_energy_ratio   Legacy feature kept for reference: fraction of total
                    spectral energy in the bird-vocalization band.
spectral_centroid   Magnitude-weighted mean frequency of the band-limited
                    spectrum, in Hz (not normalized -- unlike the other
                    features here, this is a genuinely different unit, and
                    on its own it's a weak feature; see
                    pyoperant.song_recording.variability, which tracks how
                    much it MOVES from chunk to chunk -- that turned out to
                    be a much stronger real-corpus signal than its
                    instantaneous value, see project_vocal_recorder memory).

All values are normalised to [0, 1] or near-[0, 1] ranges so they can be
combined with simple weights.

These defaults are deliberately domain-generic (a frequency band reasonable
for songbird vocalizations broadly), not tuned to any particular lab's
chambers or species -- see pyoperant/song_recording/__init__.py's package
docstring, or the guardrail discussed when this subpackage was designed.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Feature result container
# ---------------------------------------------------------------------------

@dataclass
class AudioFeatures:
    rms: float                # 0.0 – 1.0  (higher = louder)
    spectral_flatness: float  # 0.0 – 1.0  (lower = more tonal)
    onset_sharpness: float    # 0.0 – 1.0  (higher = more impulsive)
    harmonic_ratio: float     # 0.0 – 1.0  (higher = more harmonic)
    band_energy_ratio: float  # 0.0 – 1.0  (higher = more energy in band)
    spectral_centroid: float  # Hz -- NOT normalized, see class docstring above

    def as_array(self) -> np.ndarray:
        return np.array([
            self.rms,
            self.spectral_flatness,
            self.onset_sharpness,
            self.harmonic_ratio,
            self.band_energy_ratio,
            self.spectral_centroid,
        ], dtype=np.float32)

    def __repr__(self) -> str:
        return (
            f"AudioFeatures("
            f"rms={self.rms:.4f}, "
            f"flatness={self.spectral_flatness:.4f}, "
            f"onset={self.onset_sharpness:.4f}, "
            f"harmonic={self.harmonic_ratio:.4f}, "
            f"band={self.band_energy_ratio:.4f}, "
            f"centroid={self.spectral_centroid:.0f}Hz)"
        )


# ---------------------------------------------------------------------------
# Core extractor class
# ---------------------------------------------------------------------------

class FeatureExtractor:
    """
    Stateless feature extractor.  Instantiate once, call extract() per chunk.

    Parameters
    ----------
    sample_rate   : int   Audio sample rate in Hz (default 44100).
    freq_low      : int   Low edge of bird-vocalization band in Hz (default 1000).
    freq_high     : int   High edge of bird-vocalization band in Hz (default 10000).
    n_fft         : int   FFT size.  Set automatically from chunk size if None.
    n_harmonics   : int   How many harmonic multiples to check above fundamental.
    harmonic_tol  : float Fractional tolerance for harmonic peak detection (±).
    envelope_frames : int Number of sub-frames used to measure onset sharpness.
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        freq_low: int = 1000,
        freq_high: int = 10000,
        n_fft: int | None = None,
        n_harmonics: int = 6,
        harmonic_tol: float = 0.03,
        envelope_frames: int = 20,
    ):
        self.sample_rate = sample_rate
        self.freq_low = freq_low
        self.freq_high = freq_high
        self.n_harmonics = n_harmonics
        self.harmonic_tol = harmonic_tol
        self.envelope_frames = envelope_frames
        self._n_fft = n_fft   # resolved lazily on first call

        # Pre-computed frequency bin arrays — built on first call once
        # we know the chunk size.
        self._freqs: np.ndarray | None = None
        self._band_mask: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_fft_setup(self, chunk_len: int) -> None:
        """Build frequency bin lookup tables sized to this chunk."""
        if self._freqs is not None and len(self._freqs) == chunk_len // 2 + 1:
            return
        n_fft = self._n_fft if self._n_fft else chunk_len
        self._freqs = np.fft.rfftfreq(n_fft, d=1.0 / self.sample_rate)
        self._band_mask = (
            (self._freqs >= self.freq_low) & (self._freqs <= self.freq_high)
        )

    # ------------------------------------------------------------------
    # Individual feature functions (public so they can be unit-tested)
    # ------------------------------------------------------------------

    def compute_rms(self, chunk: np.ndarray) -> float:
        """Root-mean-square amplitude.  Range ≈ 0–1 for float32 audio."""
        return float(np.sqrt(np.mean(chunk ** 2)))

    def compute_spectral_flatness(
        self, magnitude: np.ndarray, eps: float = 1e-10
    ) -> float:
        """
        Wiener entropy / spectral flatness of the band-limited spectrum.

        Returns value in [0, 1]:
          ~0  → narrow-band / tonal (typical of birdsong syllables)
          ~1  → broad-band / noise-like (typical of cage noise)

        We compute it only over the vocalization band to avoid the DC
        offset and low-frequency rumble dominating the result.
        """
        band_mag = magnitude[self._band_mask] + eps
        log_mean = np.mean(np.log(band_mag))
        arith_mean = np.mean(band_mag)
        geom_mean = np.exp(log_mean)
        flatness = geom_mean / (arith_mean + eps)
        return float(np.clip(flatness, 0.0, 1.0))

    def compute_onset_sharpness(self, chunk: np.ndarray) -> float:
        """
        Impulsiveness of the amplitude envelope.

        Divide the chunk into short sub-frames, compute RMS of each,
        then return  peak_rms / (mean_rms + eps).

        Range interpretation:
          High (> 5)  → sudden transient (wire hit, feeder knock)
          Low (1–3)   → smooth amplitude envelope (song syllable)

        We normalise to [0, 1] via a soft-clip so this can be combined
        with other features directly.
        """
        frame_size = max(1, len(chunk) // self.envelope_frames)
        n_complete = len(chunk) // frame_size
        if n_complete < 2:
            return 0.0
        frames = chunk[:n_complete * frame_size].reshape(n_complete, frame_size)
        frame_rms = np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-10
        raw_sharpness = float(frame_rms.max() / frame_rms.mean())
        # Soft-normalise: values above ~10 are clamped toward 1
        normalised = 1.0 - np.exp(-0.15 * (raw_sharpness - 1.0))
        return float(np.clip(normalised, 0.0, 1.0))

    def compute_harmonic_ratio(
        self,
        magnitude: np.ndarray,
        min_fundamental: int = 500,
        max_fundamental: int = 8000,
    ) -> float:
        """
        Fraction of band energy that falls near harmonic multiples of
        the strongest spectral peak in the band.

        Algorithm
        ---------
        1. Find the bin with maximum magnitude in [min_fundamental, max_fundamental].
        2. That bin's frequency is the candidate fundamental f0.
        3. For each harmonic k = 2 … n_harmonics, look for a peak within
           ±harmonic_tol of k * f0.  Sum up matched energy.
        4. Return matched_energy / total_band_energy.

        Range: 0 (no harmonic structure) → 1 (perfect harmonic series).

        Notes
        -----
        This is intentionally simple — it uses a single-peak HPS-lite
        approach rather than a full autocorrelation pitch tracker.  It
        works well for the periodic syllables of many songbirds and runs in
        ~0.1 ms on a Pi 3B+.
        """
        freqs = self._freqs
        band_mask = self._band_mask

        fund_mask = (freqs >= min_fundamental) & (freqs <= max_fundamental)
        if not fund_mask.any():
            return 0.0

        band_mag = magnitude.copy()
        band_mag[~band_mask] = 0.0

        fund_mag = magnitude.copy()
        fund_mag[~fund_mask] = 0.0
        peak_bin = int(np.argmax(fund_mag))
        if magnitude[peak_bin] < 1e-8:
            return 0.0

        f0 = float(freqs[peak_bin])
        total_band_energy = float(band_mag.sum()) + 1e-10
        harmonic_energy = float(magnitude[peak_bin])  # fundamental itself counts

        for k in range(2, self.n_harmonics + 1):
            target_freq = k * f0
            if target_freq > self.freq_high * 1.1:
                break
            tol = target_freq * self.harmonic_tol
            h_mask = (freqs >= target_freq - tol) & (freqs <= target_freq + tol)
            if h_mask.any():
                harmonic_energy += float(magnitude[h_mask].max())

        return float(np.clip(harmonic_energy / total_band_energy, 0.0, 1.0))

    def compute_band_energy_ratio(self, magnitude: np.ndarray) -> float:
        """Fraction of total spectral energy in [freq_low, freq_high]."""
        total = magnitude.sum() + 1e-12
        band = magnitude[self._band_mask].sum()
        return float(np.clip(band / total, 0.0, 1.0))

    def compute_spectral_centroid(self, magnitude: np.ndarray) -> float:
        """Magnitude-weighted mean frequency of the band-limited spectrum,
        in Hz. Cheap -- reuses the same rfft magnitude every other
        frequency-domain feature already needs, just one more weighted
        sum over it."""
        band_mag = magnitude[self._band_mask]
        band_freqs = self._freqs[self._band_mask]
        total = band_mag.sum() + 1e-12
        return float((band_freqs * band_mag).sum() / total)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def extract(self, chunk: np.ndarray) -> AudioFeatures:
        """
        Compute all features for one audio chunk.

        Parameters
        ----------
        chunk : np.ndarray
            Mono float32 audio, any length ≥ 256 samples.

        Returns
        -------
        AudioFeatures dataclass with all five features.
        """
        self._ensure_fft_setup(len(chunk))

        rms = self.compute_rms(chunk)

        # Compute spectrum once; reuse for all frequency-domain features
        magnitude = np.abs(np.fft.rfft(chunk, n=self._n_fft))

        flatness = self.compute_spectral_flatness(magnitude)
        onset = self.compute_onset_sharpness(chunk)
        harmonic = self.compute_harmonic_ratio(magnitude)
        band = self.compute_band_energy_ratio(magnitude)
        centroid = self.compute_spectral_centroid(magnitude)

        return AudioFeatures(
            rms=rms,
            spectral_flatness=flatness,
            onset_sharpness=onset,
            harmonic_ratio=harmonic,
            band_energy_ratio=band,
            spectral_centroid=centroid,
        )


# ---------------------------------------------------------------------------
# Quick self-test / diagnostic (run directly: python -m pyoperant.song_recording.features)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sr = 44100
    duration = 0.1      # seconds
    chunk_len = int(sr * duration)
    extractor = FeatureExtractor(sample_rate=sr)
    t = np.linspace(0, duration, chunk_len, endpoint=False)

    print("=== Feature extractor diagnostics ===\n")

    # 1. Silence
    silence = np.zeros(chunk_len, dtype=np.float32)
    f = extractor.extract(silence)
    print(f"Silence:              {f}")

    # 2. Pure tone at 3 kHz (idealized birdsong syllable)
    tone = (0.1 * np.sin(2 * np.pi * 3000 * t)).astype(np.float32)
    f = extractor.extract(tone)
    print(f"Pure 3 kHz tone:      {f}")

    # 3. Harmonic stack at 2 kHz (f0 + 3 harmonics)
    harmonic = (
        0.08 * np.sin(2 * np.pi * 2000 * t) +
        0.05 * np.sin(2 * np.pi * 4000 * t) +
        0.03 * np.sin(2 * np.pi * 6000 * t) +
        0.02 * np.sin(2 * np.pi * 8000 * t)
    ).astype(np.float32)
    f = extractor.extract(harmonic)
    print(f"Harmonic 2 kHz stack: {f}")

    # 4. White noise (cage background)
    rng = np.random.default_rng(42)
    noise = (0.05 * rng.standard_normal(chunk_len)).astype(np.float32)
    f = extractor.extract(noise)
    print(f"White noise:          {f}")

    # 5. Impulse (single-sample click — cage wire hit)
    impulse = np.zeros(chunk_len, dtype=np.float32)
    impulse[chunk_len // 4] = 0.5
    impulse[chunk_len // 4 + 1] = -0.3
    f = extractor.extract(impulse)
    print(f"Impulse (click):      {f}")

    # 6. FM sweep 1–8 kHz (rough approximation of a syllable)
    freq_env = np.linspace(1000, 8000, chunk_len)
    phase = 2 * np.pi * np.cumsum(freq_env) / sr
    sweep = (0.08 * np.sin(phase)).astype(np.float32)
    f = extractor.extract(sweep)
    print(f"FM sweep 1-8 kHz:     {f}")

    print("\nExpected patterns:")
    print("  Pure tone / harmonic : low flatness, low onset, high harmonic ratio")
    print("  White noise          : high flatness, low onset sharpness")
    print("  Impulse              : moderate flatness, HIGH onset sharpness")
    print("  FM sweep             : low-moderate flatness, moderate harmonic")
