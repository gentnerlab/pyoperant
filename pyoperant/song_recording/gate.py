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
from pyoperant.song_recording.variability import RollingVariabilityTracker, VariabilityConfig

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

    # Weighted score feature weights (should sum to 1.0).
    # weight_variability added 2026-09-08 on real evidence -- a causal,
    # short-window (0.5-2.0s) rolling variability signal (see
    # pyoperant.song_recording.variability) scored mean AUC 0.82 against
    # the lab's real 54-bird curated corpus, matching or beating every
    # legacy feature here including the best of them (harmonic_ratio,
    # 0.756 mean AUC across that same 54-bird corpus). That corpus result
    # is real but describes bout-level average behavior across many
    # birds/chambers -- it does NOT hold at the instantaneous, per-100ms-
    # chunk level on this lab's actual UMIK-1/chamber hardware. Confirmed
    # live 2026-09-21 (project_vocal_recorder memory): replaying real
    # confirmed-song clips from a live deployment (B1504) through this
    # exact gate showed harmonic_ratio pinned near 0 (0.01-0.05, never
    # above 0.15) even on the loudest, clearest singing chunks -- it was
    # contributing essentially nothing to the composite score, and on 3
    # of 4 real song clips this was enough to drag borderline chunks below
    # threshold and cause the clip to release (cut off) while the bird was
    # still audibly singing. weight_harmonic cut 0.20 -> 0.05 in response
    # (kept nonzero rather than zeroed, since a cleaner/less-reverberant
    # chamber could still get real signal from it).
    #
    # Where the freed 0.15 goes was NOT the first guess -- two earlier
    # attempts were caught by testing, not assumed safe:
    #  1. Proportional redistribution across all four remaining weights
    #     looked fine against real song/noise clips, but the gate's own
    #     synthetic self-test (`python -m pyoperant.song_recording.gate`)
    #     caught a real regression: steady-state pure white noise, whose
    #     onset_sharpness apparently scores as deceptively "sharp"
    #     (sub_onset ~0.98 -- onset_sharpness itself near 0, and
    #     sub_onset = 1 - onset_sharpness), started passing the gate
    #     (score 0.385 -> 0.456) purely because weight_onset went up.
    #  2. Routing the freed weight into ONLY weight_flatness/weight_band
    #     (7:3, matching their prior 0.28:0.12 ratio) fixed that -- but a
    #     second, subtler edge case then showed up: the self-test's own
    #     case sequence (silence -> tone -> harmonic -> sweep -> quiet
    #     noise -> louder noise -> white noise, one shared gate instance)
    #     lets the variability tracker's rolling window pick up artificial
    #     "variability" purely from jumping between unrelated signal types
    #     in immediate succession -- var drifts from a neutral 0.50 up to
    #     0.67 by the time white noise is reached, vs. 0.50 for the SAME
    #     white noise fed steady-state to a fresh gate. That inflated var,
    #     combined with the weight_band boost, pushed white noise's score
    #     from 0.424 (OLD, correctly fails) to 0.457 (a bare pass) -- a
    #     real, if narrow, erosion of safety margin against exactly the
    #     kind of transition a real deployment does see (e.g. right after
    #     a bird stops singing and the room goes quiet).
    #  Final choice: route the freed 0.15 into weight_flatness ONLY,
    #  leaving weight_band untouched at its prior 0.12. flatness is
    #  unambiguously low on both quiet AND loud white noise (0.15 either
    #  way) and unambiguously high on every real tonal/harmonic synthetic
    #  case, whereas band_energy_ratio is inherently more ambiguous for
    #  broadband signals in general -- boosting the unambiguous feature
    #  instead of the ambiguous one. Re-tested end to end: identical fix on
    #  all 4 real song clips (release eliminated entirely on 3/4, barely
    #  moved on the 4th), the real confirmed-noise clip's behavior
    #  unchanged, isolated steady-state white noise correctly rejected
    #  (score 0.414), and even the self-test's own artificial worst-case
    #  sequential-warm-up white noise still correctly rejected (score
    #  0.445, under the 0.45 threshold -- a thinner margin than OLD's
    #  0.424, but still on the right side of it). weight_onset and
    #  weight_variability are untouched.
    #
    # The other four weights below are shaved down PROPORTIONALLY
    # (multiplied by 0.8, preserving their relative weighting exactly as
    # before) to make room for weight_variability -- a deliberately
    # mechanical, conservative redistribution, not an independent
    # re-tuning of flatness/onset/band individually (that's still a
    # separate, not-yet-made decision -- see project_vocal_recorder
    # memory).
    weight_flatness:     float = 0.43
    weight_onset:        float = 0.20
    weight_harmonic:     float = 0.05
    weight_band:         float = 0.12
    weight_variability:  float = 0.20

    # Weighted score threshold
    threshold: float = 0.45

    # Vocalization band
    freq_low:  int = 1000
    freq_high: int = 10000

    def __post_init__(self):
        total = (self.weight_flatness + self.weight_onset
                 + self.weight_harmonic + self.weight_band
                 + self.weight_variability)
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
            weight_variability    = d.get("weight_variability",    cls.weight_variability),
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
    sub_variability: float = 0.0    # from RollingVariabilityTracker, see variability.py

    def __repr__(self) -> str:
        nm = f"snr={self.snr_score:.2f}" if self.noise_model_ok else "no-model"
        status = "PASS" if self.passed else "fail"
        return (
            f"GateResult({status} score={self.score:.3f} {nm} | "
            f"flat={self.sub_flatness:.2f} "
            f"onset={self.sub_onset:.2f} "
            f"harm={self.sub_harmonic:.2f} "
            f"band={self.sub_band:.2f} "
            f"var={self.sub_variability:.2f})"
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
        variability_config:      VariabilityConfig | None = None,
    ):
        self.config = config or GateConfig()
        self.noise_model = noise_model
        # Resolved once here (from the real config, via make_gate_from_config)
        # rather than rebuilt from an empty dict inside score() -- a
        # previous version of this gate did that and silently ignored
        # whatever snr_score_threshold was actually configured.
        self.noise_model_gate_config = noise_model_gate_config or NoiseModelGateConfig()
        # One tracker per gate instance -- it's genuinely stateful across
        # the whole session's stream of chunks (unlike score(), which stays
        # a pure function of its arguments). See variability.py.
        self.variability_tracker = RollingVariabilityTracker(variability_config)
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
        features:          AudioFeatures,
        magnitude:         np.ndarray | None = None,
        variability_score: float = 0.0,
    ) -> GateResult:
        """
        Score a chunk given pre-extracted features.

        Parameters
        ----------
        features  : from FeatureExtractor.extract()
        magnitude : rfft magnitude (needed for noise-model gate).
                    If None, falls back to fixed RMS floor for stage 1.
        variability_score : from RollingVariabilityTracker.update(), called
                    by evaluate() -- pass explicitly (like magnitude) rather
                    than have score() reach into gate state, so this stays
                    a plain function of its arguments and is easy to test
                    directly with a fixed value, no tracker/history needed.
                    Defaults to 0.0 (neutral/no-signal) for direct score()
                    calls that don't go through evaluate().
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
        sub_var   = float(np.clip(variability_score, 0.0, 1.0))

        weighted = float(np.clip(
            cfg.weight_flatness    * sub_flat  +
            cfg.weight_onset       * sub_onset +
            cfg.weight_harmonic    * sub_harm  +
            cfg.weight_band        * sub_band  +
            cfg.weight_variability * sub_var,
            0.0, 1.0,
        ))

        return GateResult(
            passed          = weighted >= cfg.threshold,
            score           = weighted,
            features        = features,
            snr_score       = snr_score,
            noise_model_ok  = noise_model_ok,
            sub_flatness    = sub_flat,
            sub_onset       = sub_onset,
            sub_harmonic    = sub_harm,
            sub_band        = sub_band,
            sub_variability = sub_var,
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
            spectral_centroid = extractor.compute_spectral_centroid(magnitude),
        )

        # Update the rolling variability tracker every chunk (even ones that
        # will fail stage 1/the band-energy floor below) so its window
        # reflects the real, continuous audio stream rather than only the
        # chunks that happened to pass earlier gates.
        variability_score = self.variability_tracker.update({
            "band_energy_ratio": features.band_energy_ratio,
            "spectral_centroid": features.spectral_centroid,
        })

        return self.score(features, magnitude=magnitude, variability_score=variability_score)


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
    var_cfg     = VariabilityConfig.from_config_dict(cfg)
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

    gate = SongGate(gate_cfg, noise_model=noise_model, noise_model_gate_config=nm_gate_cfg,
                    variability_config=var_cfg)
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

    # ── Variability integration check ───────────────────────────────────
    # The cases above are each a single, isolated chunk -- fine for the
    # other features, but variability needs a SEQUENCE to say anything
    # (see variability.py's own self-test for the tracker in isolation).
    # This checks the full evaluate() wiring end-to-end: a real gate
    # instance, fed a real sequence, should show its variability sub-score
    # ramp up as the rolling window fills on a modulated ("song-like")
    # amplitude-modulated tone, and stay low on a steady tone at the same
    # average loudness/frequency.
    print("\n=== Variability sub-score over a sequence (end-to-end evaluate() check) ===")
    gate_var = SongGate(GateConfig(threshold=0.45))
    extractor_var = FeatureExtractor(sample_rate=sr)
    tone_3k   = (0.06 * np.sin(2 * np.pi * 3000 * t)).astype(np.float32)
    lowfreq   = (0.06 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)  # OUT of [freq_low,freq_high]

    # Note: amplitude modulation alone does NOT move band_energy_ratio or
    # spectral_centroid (scaling every bin together changes neither the
    # in-band/out-of-band energy RATIO nor the weighted-mean frequency) --
    # the signal has to actually change SHAPE. Mixing in a fixed-frequency
    # out-of-band component at a varying relative amplitude swings
    # band_energy_ratio while barely moving spectral_centroid (confirmed:
    # pure tone centroid=3000.0003Hz, tone+lowfreq mix centroid=3000.0005Hz).
    print("Modulated mix (in-band tone + swinging out-of-band component, "
          "band_energy_ratio should swing):")
    for i in range(25):
        mix = 0.5 + 0.45 * np.sin(i * 0.8)  # 0.05..0.95, swings the out-of-band fraction
        chunk = (tone_3k + mix * lowfreq).astype(np.float32)
        r = gate_var.evaluate(chunk, extractor_var)
        if i in (1, 5, 10, 20, 24):
            print(f"  chunk {i:2d}: band_energy_ratio={r.features.band_energy_ratio:.3f} "
                  f"score={r.score:.3f} sub_variability={r.sub_variability:.3f}")

    print("Steady mix (same components, constant proportion, no modulation):")
    gate_var2 = SongGate(GateConfig(threshold=0.45))
    for i in range(25):
        chunk = (tone_3k + 0.5 * lowfreq).astype(np.float32)
        r = gate_var2.evaluate(chunk, extractor_var)
        if i in (1, 5, 10, 20, 24):
            print(f"  chunk {i:2d}: band_energy_ratio={r.features.band_energy_ratio:.3f} "
                  f"score={r.score:.3f} sub_variability={r.sub_variability:.3f}")

    print("\nExpected: the modulated mix's sub_variability should climb well above the "
          "steady mix's -- note the steady case settles at 0.5, not 0: with zero "
          "measured variability, band_energy_ratio's own sub-score is 0 (no signal) "
          "but spectral_centroid's is 1 (inverted -- see variability.py, its "
          "invert=True means LOW variability scores HIGH), and the combined score is "
          "their mean. Confirms the tracker is really wired into evaluate()'s "
          "per-chunk hot path, not just working in variability.py's own isolated "
          "self-test.")
