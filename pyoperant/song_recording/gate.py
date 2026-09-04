"""
gate.py — Fast signal-processing gate for birdsong detection.

Two-stage architecture
----------------------
Stage 1 — Noise-model gate (when a NoiseModel is available)
    Compare the chunk's per-bin spectrum against the learned per-chamber
    noise floor.  Falls back to fixed RMS floor if no model is loaded.

Stage 2 — Weighted acoustic feature score
    Spectral flatness, onset sharpness, harmonic ratio, band energy ratio.
    Runs regardless of noise model.  Rejects broadband noise that sits above
    the noise floor but lacks harmonic/tonal structure.

pyoperant integration
---------------------
    from pyoperant.song_recording.noise_model import NoiseModel
    from pyoperant.song_recording.gate import SongGate, GateConfig, make_gate_from_config

    model = NoiseModel.load("noise_model.npz")
    gate, extractor = make_gate_from_config(cfg, noise_model=model)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pyoperant.song_recording.features import AudioFeatures, FeatureExtractor
from pyoperant.song_recording.noise_model import NoiseModelGateConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gate configuration
# ---------------------------------------------------------------------------

@dataclass
class GateConfig:
    # Fixed RMS floor — used when no noise model is loaded
    rms_floor: float = 0.003

    # Hard band-energy floor — rejects pure low-frequency sources
    min_band_energy_ratio: float = 0.10

    # Weighted score feature weights (should sum to 1.0)
    weight_flatness:  float = 0.35
    weight_onset:     float = 0.25
    weight_harmonic:  float = 0.25
    weight_band:      float = 0.15

    # Weighted score threshold
    threshold: float = 0.45

    # Vocalization band
    freq_low:  int = 1000
    freq_high: int = 10000

    def __post_init__(self):
        total = (self.weight_flatness + self.weight_onset
                 + self.weight_harmonic + self.weight_band)
        if not np.isclose(total, 1.0, atol=0.01):
            log.warning("GateConfig weights sum to %.3f, not 1.0.", total)

    @classmethod
    def from_config_dict(cls, cfg: dict) -> "GateConfig":
        d = cfg.get("gate", {})
        return cls(
            rms_floor             = d.get("rms_floor",             cls.rms_floor),
            min_band_energy_ratio = d.get("min_band_energy_ratio", cls.min_band_energy_ratio),
            weight_flatness       = d.get("weight_flatness",       cls.weight_flatness),
            weight_onset          = d.get("weight_onset",          cls.weight_onset),
            weight_harmonic       = d.get("weight_harmonic",       cls.weight_harmonic),
            weight_band           = d.get("weight_band",           cls.weight_band),
            threshold             = d.get("threshold",             cls.threshold),
            freq_low              = cfg.get("freq_low",            cls.freq_low),
            freq_high             = cfg.get("freq_high",           cls.freq_high),
        )


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    passed:         bool
    score:          float           # weighted feature score [0,1]
    features:       AudioFeatures
    snr_score:      float = 0.0     # noise-model band SNR score (0 if no model)
    noise_model_ok: bool  = False   # True when noise model gate was used
    sub_flatness:   float = 0.0
    sub_onset:      float = 0.0
    sub_harmonic:   float = 0.0
    sub_band:       float = 0.0

    def __repr__(self) -> str:
        nm = f"snr={self.snr_score:.2f}" if self.noise_model_ok else "no-model"
        status = "PASS" if self.passed else "fail"
        return (
            f"GateResult({status} score={self.score:.3f} {nm} | "
            f"flat={self.sub_flatness:.2f} "
            f"onset={self.sub_onset:.2f} "
            f"harm={self.sub_harmonic:.2f} "
            f"band={self.sub_band:.2f})"
        )


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

class SongGate:
    """
    Two-stage birdsong detection gate.

    Stage 1: Spectral SNR against learned noise floor (or fixed RMS fallback).
    Stage 2: Weighted acoustic feature score.
    """

    def __init__(
        self,
        config:                  GateConfig | None = None,
        noise_model:             "NoiseModel | None" = None,
        noise_model_gate_config: NoiseModelGateConfig | None = None,
    ):
        self.config = config or GateConfig()
        self.noise_model = noise_model
        # Resolved once here (from the real config, via make_gate_from_config)
        # rather than rebuilt from an empty dict inside score() -- a
        # previous version of this gate did that and silently ignored
        # whatever snr_score_threshold was actually configured.
        self.noise_model_gate_config = noise_model_gate_config or NoiseModelGateConfig()
        if noise_model is not None:
            log.info("SongGate: noise model loaded — %s", noise_model.summary())
        else:
            log.info("SongGate: no noise model, using fixed RMS floor=%.4f",
                     self.config.rms_floor)

    # ── Model management ──────────────────────────────────────────────────

    def load_noise_model(self, path: str | Path) -> None:
        from pyoperant.song_recording.noise_model import NoiseModel
        self.noise_model = NoiseModel.load(path)
        log.info("Noise model loaded: %s", self.noise_model.summary())

    def clear_noise_model(self) -> None:
        self.noise_model = None
        log.info("Noise model cleared; reverting to fixed RMS floor.")

    @property
    def has_noise_model(self) -> bool:
        return self.noise_model is not None

    # ── Scoring ───────────────────────────────────────────────────────────

    def score(
        self,
        features:  AudioFeatures,
        magnitude: np.ndarray | None = None,
    ) -> GateResult:
        """
        Score a chunk given pre-extracted features.

        Parameters
        ----------
        features  : from FeatureExtractor.extract()
        magnitude : rfft magnitude (needed for noise-model gate).
                    If None, falls back to fixed RMS floor for stage 1.
        """
        cfg            = self.config
        snr_score      = 0.0
        noise_model_ok = False

        # ── Stage 1 ───────────────────────────────────────────────────────
        if self.noise_model is not None and magnitude is not None:
            snr_score      = self.noise_model.band_snr_score(magnitude)
            noise_model_ok = True
            if snr_score < self.noise_model_gate_config.snr_score_threshold:
                return GateResult(
                    passed=False, score=0.0, features=features,
                    snr_score=snr_score, noise_model_ok=True,
                )
        else:
            if features.rms < cfg.rms_floor:
                return GateResult(
                    passed=False, score=0.0, features=features,
                )

        # ── Hard band-energy floor (always) ───────────────────────────────
        if features.band_energy_ratio < cfg.min_band_energy_ratio:
            return GateResult(
                passed=False, score=0.0, features=features,
                snr_score=snr_score, noise_model_ok=noise_model_ok,
            )

        # ── Stage 2: weighted feature score ───────────────────────────────
        sub_flat  = 1.0 - features.spectral_flatness
        sub_onset = 1.0 - features.onset_sharpness
        sub_harm  = features.harmonic_ratio
        sub_band  = features.band_energy_ratio

        weighted = float(np.clip(
            cfg.weight_flatness  * sub_flat  +
            cfg.weight_onset     * sub_onset +
            cfg.weight_harmonic  * sub_harm  +
            cfg.weight_band      * sub_band,
            0.0, 1.0,
        ))

        return GateResult(
            passed         = weighted >= cfg.threshold,
            score          = weighted,
            features       = features,
            snr_score      = snr_score,
            noise_model_ok = noise_model_ok,
            sub_flatness   = sub_flat,
            sub_onset      = sub_onset,
            sub_harmonic   = sub_harm,
            sub_band       = sub_band,
        )

    def evaluate(
        self,
        chunk:     np.ndarray,
        extractor: FeatureExtractor,
    ) -> GateResult:
        """
        Compute FFT once, extract features, and score — the main hot path.
        Called on every 100 ms audio chunk by monitor.py.
        """
        extractor._ensure_fft_setup(len(chunk))
        n_fft     = extractor._n_fft or len(chunk)
        magnitude = np.abs(np.fft.rfft(chunk, n=n_fft))

        features = AudioFeatures(
            rms               = extractor.compute_rms(chunk),
            spectral_flatness = extractor.compute_spectral_flatness(magnitude),
            onset_sharpness   = extractor.compute_onset_sharpness(chunk),
            harmonic_ratio    = extractor.compute_harmonic_ratio(magnitude),
            band_energy_ratio = extractor.compute_band_energy_ratio(magnitude),
        )

        return self.score(features, magnitude=magnitude)


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def make_gate_from_config(
    cfg: dict,
    noise_model: "NoiseModel | None" = None,
) -> tuple["SongGate", FeatureExtractor]:
    """
    Build a (gate, extractor) pair from a song_recording config dict (see
    pyoperant.behavior.lights).

    If noise_model is None, attempts to auto-load from noise_model.model_path
    if that file exists.
    """
    gate_cfg    = GateConfig.from_config_dict(cfg)
    nm_gate_cfg = NoiseModelGateConfig.from_config_dict(cfg)
    extractor = FeatureExtractor(
        sample_rate = cfg.get("sample_rate", 44100),
        freq_low    = cfg.get("freq_low",    1000),
        freq_high   = cfg.get("freq_high",   10000),
    )

    if noise_model is None:
        nc         = cfg.get("noise_model", {})
        model_path = Path(nc.get("model_path", "noise_model.npz"))
        if model_path.exists():
            try:
                from pyoperant.song_recording.noise_model import NoiseModel
                noise_model = NoiseModel.load(model_path)
            except Exception as exc:
                log.warning("Could not auto-load noise model from %s: %s", model_path, exc)

    gate = SongGate(gate_cfg, noise_model=noise_model, noise_model_gate_config=nm_gate_cfg)
    return gate, extractor


# ---------------------------------------------------------------------------
# Self-test (run directly: python -m pyoperant.song_recording.gate)
# Synthetic signals only -- no microphone/hardware required.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pyoperant.song_recording.noise_model import _build_model

    sr        = 44100
    dur       = 0.1
    chunk_len = int(sr * dur)
    t         = np.linspace(0, dur, chunk_len, endpoint=False)
    rng       = np.random.default_rng(42)

    # Simulate calibration noise (quiet broadband, mimics chamber background)
    freqs     = np.fft.rfftfreq(chunk_len, d=1.0 / sr)
    band_mask = (freqs >= 1000) & (freqs <= 10000)
    sim_noise = [(0.005 * rng.standard_normal(chunk_len)).astype(np.float32)
                 for _ in range(60)]
    noise_model = _build_model(
        chunks=sim_noise, freqs=freqs, band_mask=band_mask,
        sample_rate=sr, n_fft=chunk_len,
        freq_low=1000, freq_high=10000,
        sensitivity_k=3.0, device_id="sim",
    )

    extractor    = FeatureExtractor(sample_rate=sr)
    gate_with    = SongGate(GateConfig(threshold=0.45), noise_model=noise_model)
    gate_without = SongGate(GateConfig(threshold=0.45))

    cases = {
        "Silence":                np.zeros(chunk_len, np.float32),
        "Pure 3 kHz (strong)":   (0.05 * np.sin(2*np.pi*3000*t)).astype(np.float32),
        "Harmonic 2 kHz":        (0.04*np.sin(2*np.pi*2000*t) +
                                  0.02*np.sin(2*np.pi*4000*t) +
                                  0.01*np.sin(2*np.pi*6000*t)).astype(np.float32),
        "FM sweep 1-8 kHz":      (0.04*np.sin(
                                   2*np.pi*np.cumsum(np.linspace(1000,8000,chunk_len))/sr
                                  )).astype(np.float32),
        "Noise at floor level":  (0.005*rng.standard_normal(chunk_len)).astype(np.float32),
        "Noise 3× floor":        (0.015*rng.standard_normal(chunk_len)).astype(np.float32),
        "White noise (loud)":    (0.04*rng.standard_normal(chunk_len)).astype(np.float32),
        "Low-freq rumble":       (0.06*np.sin(2*np.pi*100*t)).astype(np.float32),
        "Impulse (cage wire)":   (lambda a: (a.__setitem__(chunk_len//4, 0.4) or a)
                                  )(np.zeros(chunk_len, np.float32)),
    }

    print("=== Gate diagnostics ===\n")
    print(f"  {'Signal':<28}  {'With NM':>8}  {'Without NM':>10}")
    print("  " + "-"*52)
    for name, chunk in cases.items():
        rw = gate_with.evaluate(chunk, extractor)
        rn = gate_without.evaluate(chunk, extractor)
        print(f"  {name:<28}  {'PASS' if rw.passed else 'fail':>8}  {'PASS' if rn.passed else 'fail':>10}")

    print("\nNote: 'Noise 3x floor' should fail WITH model (below SNR threshold)")
    print("but may pass WITHOUT model (above fixed RMS floor).")
    print("This is the key improvement: adaptive rejection of chamber-specific noise.")
