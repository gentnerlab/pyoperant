"""
variability.py — Rolling-window temporal variability of acoustic features.

Why this exists
----------------
Phase E analysis against the lab's real, curated starling corpus (5355
labeled bouts, 54 birds -- see project_vocal_recorder memory) found that
several features' variability ACROSS a bout (std) was a stronger
song/not-song signal than their average value -- e.g. spectral_centroid_std
(mean AUC 0.80) clearly beat spectral_centroid's own mean, across many
birds/chambers, not just one recording.

That finding used the WHOLE bout with total hindsight, which a live,
causal gate can never have. A follow-up check recomputed the same idea
using only a short CAUSAL rolling window (the recent past, nothing else)
at a few window sizes, and found the signal survives losing hindsight
almost entirely -- for band_energy_ratio it actually did BETTER causally
(mean AUC 0.819 at a 2.0s window vs. 0.779 for the full-bout, hindsight
version). That result is what justified building this as a real-time gate
feature rather than parking the idea until a CNN with a wider temporal
receptive field.

Deliberately its own module, not part of smoother.py: smoother.py's own
docstring is explicit that it's generic, clip-agnostic temporal smoothing
of the gate's final pass/fail DECISION. This tracks raw acoustic
sub-features themselves across a short window -- feature-domain territory,
same category as features.py/gate.py, not decision-smoothing.

pyoperant integration
----------------------
    from pyoperant.song_recording.variability import RollingVariabilityTracker

    tracker = RollingVariabilityTracker()
    score = tracker.update({"band_energy_ratio": ..., "spectral_centroid": ...})

SongGate owns one instance and updates it once per chunk inside evaluate()
(see gate.py); score() takes the resulting normalized value as a plain
argument, the same way it already takes `magnitude`, so score() itself
stays a pure function of its inputs.
"""

from __future__ import annotations

import collections
import logging
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class TrackedFeatureConfig:
    """
    One tracked feature's rolling-window + normalization settings.

    window_chunks   How many recent chunks' values to keep. Validated on
                    real 48kHz/100ms-chunk corpus data at 5/10/20 chunks
                    (0.5/1.0/2.0s) -- the module-level defaults below use
                    whichever window size empirically won for that
                    specific feature, not one size for everything.
    scale           Raw rolling-std value that maps to ~1.0 after
                    normalization (larger values are clipped to 1.0).
                    Derived from the real corpus's own ~95th-percentile
                    rolling std across both classes, not guessed.
    invert          If True, HIGHER raw variability means LOWER sub-score.
                    Needed because "more variable" isn't always "more
                    song-like": on the real corpus, higher
                    spectral_centroid variability was actually more
                    characteristic of NOT-song (cage noise jitters the
                    centroid more than song does) -- the opposite
                    direction from band_energy_ratio, where song is the
                    more variable class.
    """
    window_chunks: int
    scale: float
    invert: bool = False


# Empirical defaults, real starling corpus, 2026-09-08 (see module docstring):
#   band_energy_ratio: song is MORE variable. Best window 20 chunks (2.0s),
#     mean AUC 0.819 (beat the 0.779 non-causal full-bout number).
#   spectral_centroid: NOT-song is MORE variable (hence invert=True). Best
#     window 5 chunks (0.5s), mean AUC 0.817 (vs. 0.802 full-bout).
# Deliberately domain-generic in STRUCTURE (which features, what shape of
# normalization) even though these specific numbers came from one lab's
# starling corpus -- see feedback_pyoperant_public_repo_boundary. Treat
# `scale` especially as a starting point to recalibrate against a new
# corpus/species, not a universal constant.
DEFAULT_TRACKED_FEATURES: dict = {
    "band_energy_ratio": TrackedFeatureConfig(window_chunks=20, scale=0.236, invert=False),
    "spectral_centroid": TrackedFeatureConfig(window_chunks=5, scale=1400.0, invert=True),
}


@dataclass
class VariabilityConfig:
    tracked: dict = field(default_factory=lambda: dict(DEFAULT_TRACKED_FEATURES))

    @classmethod
    def from_config_dict(cls, cfg: dict) -> "VariabilityConfig":
        d = cfg.get("variability", {})
        if not d:
            return cls()
        tracked = {}
        for name, default in DEFAULT_TRACKED_FEATURES.items():
            fd = d.get(name, {})
            tracked[name] = TrackedFeatureConfig(
                window_chunks=fd.get("window_chunks", default.window_chunks),
                scale=fd.get("scale", default.scale),
                invert=fd.get("invert", default.invert),
            )
        return cls(tracked=tracked)


class RollingVariabilityTracker:
    """
    Maintains a short rolling window of recent per-chunk values for each
    tracked feature, and reports one combined, normalized [0, 1]
    "variability score" (higher = more song-like) each time update() is
    called with the current chunk's feature values.

    Usage
    -----
        tracker = RollingVariabilityTracker()
        for chunk in audio_stream:
            features = extractor.extract(chunk)
            score = tracker.update({
                "band_energy_ratio": features.band_energy_ratio,
                "spectral_centroid": features.spectral_centroid,
            })
    """

    def __init__(self, config: "VariabilityConfig | None" = None):
        self.config = config or VariabilityConfig()
        self._buffers = {
            name: collections.deque(maxlen=tc.window_chunks)
            for name, tc in self.config.tracked.items()
        }
        self.last_sub_scores = {name: 0.0 for name in self.config.tracked}

    def reset(self) -> None:
        """Clear all rolling-window state. Not required between pyoperant
        sessions today (a fresh SongMonitor/SongGate is built per session,
        which already starts with empty buffers) -- provided for symmetry
        with FrameSmoother.reset() and for tests."""
        for buf in self._buffers.values():
            buf.clear()
        self.last_sub_scores = {name: 0.0 for name in self.config.tracked}

    def update(self, feature_values: dict) -> float:
        """
        Ingest one chunk's tracked feature values.

        Parameters
        ----------
        feature_values : dict   {feature_name: raw_value}. A missing key
                         just skips updating that feature's buffer this
                         chunk (its last known sub-score carries over).

        Returns
        -------
        Combined variability score in [0, 1] -- the mean of each tracked
        feature's own normalized sub-score. 0.0 for any feature whose
        buffer hasn't filled to at least 2 samples yet (not enough history
        to estimate variability), so the combined score naturally ramps up
        over the first `window_chunks` calls rather than starting biased.
        """
        sub_scores = []
        for name, tc in self.config.tracked.items():
            value = feature_values.get(name)
            buf = self._buffers[name]
            if value is not None:
                buf.append(value)
            if len(buf) < 2:
                sub = 0.0
            else:
                raw_std = float(np.std(buf))
                normalized = float(np.clip(raw_std / tc.scale, 0.0, 1.0))
                sub = (1.0 - normalized) if tc.invert else normalized
            self.last_sub_scores[name] = sub
            sub_scores.append(sub)
        return float(np.mean(sub_scores)) if sub_scores else 0.0


# ---------------------------------------------------------------------------
# Self-test (run directly: python -m pyoperant.song_recording.variability)
# Synthetic signals only -- no microphone/hardware required.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== RollingVariabilityTracker diagnostics ===\n")

    tracker = RollingVariabilityTracker()

    # A "song-like" sequence: band_energy_ratio swings widely (modulated),
    # spectral_centroid stays fairly steady (low jitter).
    rng = np.random.default_rng(0)
    print("Song-like sequence (high band-energy variation, steady centroid):")
    for i in range(25):
        ber = 0.5 + 0.35 * np.sin(i * 0.7) + 0.02 * rng.standard_normal()
        centroid = 3000 + 50 * rng.standard_normal()
        score = tracker.update({"band_energy_ratio": ber, "spectral_centroid": centroid})
        if i in (1, 5, 10, 20, 24):
            print(f"  chunk {i:2d}: band_energy_ratio={ber:.3f} centroid={centroid:.0f}Hz "
                  f"-> variability_score={score:.3f} sub={tracker.last_sub_scores}")

    print("\nNoise-like sequence (steady band-energy, jittery centroid):")
    tracker.reset()
    for i in range(25):
        ber = 0.3 + 0.02 * rng.standard_normal()
        centroid = 3000 + 900 * rng.standard_normal()
        score = tracker.update({"band_energy_ratio": ber, "spectral_centroid": centroid})
        if i in (1, 5, 10, 20, 24):
            print(f"  chunk {i:2d}: band_energy_ratio={ber:.3f} centroid={centroid:.0f}Hz "
                  f"-> variability_score={score:.3f} sub={tracker.last_sub_scores}")

    print("\nExpected: song-like sequence's score should climb toward ~1.0 as the "
          "band_energy_ratio window fills (high variability = song-like there); "
          "noise-like sequence's score should stay low (steady band energy, and its "
          "jittery centroid is INVERTED so high centroid variability also pulls the "
          "score down, not up).")
