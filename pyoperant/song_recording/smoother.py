"""
smoother.py — Temporal smoothing for detection decisions.

Why temporal smoothing?
-----------------------
Both the gate and a future CNN classifier operate on short windows
(~100-500 ms). A single anomalous frame can occasionally produce a false
positive: a loud cage rattle might briefly pass the gate, or a classifier
might misclassify one atypical chunk.

Real birdsong, however, spans multiple consecutive frames -- syllables and
phrases typically last several hundred ms to a few seconds, well beyond one
frame. If we require that several consecutive (or near-consecutive) frames
pass before we declare a detection, we eliminate the vast majority of
single-frame false positives without meaningfully delaying onset detection.

Two smoothers are provided
--------------------------
FrameSmoother   A simple rolling-window vote: require K-of-N recent frames
                to pass before triggering, and require M-of-N to remain
                passing to keep recording.  Cheap, interpretable, no state
                beyond the circular buffer.

ScoreSmoother   Maintains an exponential moving average of raw confidence
                scores (from the gate or a future CNN classifier), with
                separate attack and release time constants.  More suitable
                when the upstream source produces a continuous score rather
                than a binary pass/fail.  Triggers when the smoothed score
                crosses a threshold.

In the current pipeline both smoothers are available; FrameSmoother is
used with the gate output, and ScoreSmoother is reserved for a future
classifier confidence score.
"""

from __future__ import annotations

import collections
import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared result type
# ---------------------------------------------------------------------------

@dataclass
class SmootherResult:
    triggered: bool         # Should we start/continue recording?
    smoothed_score: float   # Smoothed probability / vote fraction in [0, 1]
    raw_score: float        # Most recent raw input score


# ---------------------------------------------------------------------------
# FrameSmoother — rolling majority vote
# ---------------------------------------------------------------------------

@dataclass
class FrameSmootherConfig:
    """
    Parameters for the rolling-window frame vote smoother.

    window_size     Total number of recent frames to consider.
    onset_k         Frames that must pass to START a detection
                    (out of window_size).
    sustain_k       Frames that must pass to CONTINUE a detection
                    (out of window_size, checked when already triggered).
    release_k       Frames that must fail to END a detection.
                    Defaults to window_size - sustain_k + 1 if not set.
    """
    window_size:  int   = 10
    onset_k:      int   = 6    # 6/10 frames must pass to trigger
    sustain_k:    int   = 4    # 4/10 to keep recording once triggered
    release_k:    int | None = None   # auto-computed if None

    def __post_init__(self):
        if self.onset_k > self.window_size:
            raise ValueError(
                f"onset_k ({self.onset_k}) must be ≤ window_size ({self.window_size})"
            )
        if self.sustain_k > self.window_size:
            raise ValueError(
                f"sustain_k ({self.sustain_k}) must be ≤ window_size ({self.window_size})"
            )
        if self.release_k is None:
            self.release_k = self.window_size - self.sustain_k + 1

    @classmethod
    def from_config_dict(cls, cfg: dict) -> "FrameSmootherConfig":
        d = cfg.get("frame_smoother", {})
        obj = cls(
            window_size = d.get("window_size", cls.window_size),
            onset_k     = d.get("onset_k",     cls.onset_k),
            sustain_k   = d.get("sustain_k",   cls.sustain_k),
            release_k   = d.get("release_k",   None),
        )
        return obj


class FrameSmoother:
    """
    Rolling-window majority-vote smoother.

    State machine
    -------------
    IDLE      → look for onset_k passes in last window_size frames
    TRIGGERED → look for release_k failures to exit; otherwise sustain

    Example with window=10, onset_k=6, sustain_k=4
    -----------------------------------------------
    If 6 of the last 10 frames passed the gate: TRIGGER
    While triggered: if < 4 of last 10 pass: RELEASE (go IDLE)
    This gives ~500 ms onset latency and ~600 ms release lag
    (at 100 ms chunks).

    Usage
    -----
        smoother = FrameSmoother()
        for chunk in audio_stream:
            gate_result = gate.evaluate(chunk, extractor)
            sr = smoother.update(gate_result.passed, gate_result.score)
            if sr.triggered:
                record(chunk)
    """

    def __init__(self, config: FrameSmootherConfig | None = None):
        self.config  = config or FrameSmootherConfig()
        self._buffer: collections.deque[bool] = collections.deque(
            maxlen=self.config.window_size
        )
        self._scores: collections.deque[float] = collections.deque(
            maxlen=self.config.window_size
        )
        self.triggered = False

    def reset(self) -> None:
        """Clear all state.  Call between recording sessions if needed."""
        self._buffer.clear()
        self._scores.clear()
        self.triggered = False

    def update(self, passed: bool, score: float = 1.0) -> SmootherResult:
        """
        Ingest one frame result and update the smoother state.

        Parameters
        ----------
        passed : bool   Whether the gate (or classifier) passed this frame.
        score  : float  Raw confidence score for this frame (used for
                        smoothed_score output; does not affect the vote).

        Returns
        -------
        SmootherResult with .triggered indicating whether to record.
        """
        self._buffer.append(passed)
        self._scores.append(score)

        n_pass  = sum(self._buffer)
        n_total = len(self._buffer)
        vote_fraction = n_pass / max(n_total, 1)
        smoothed = float(np.mean(list(self._scores)))

        if not self.triggered:
            # Need onset_k passes in the window to start
            if n_total >= self.config.window_size and n_pass >= self.config.onset_k:
                self.triggered = True
                log.debug(
                    "FrameSmoother: ONSET (%.0f%% of window passed)",
                    100 * vote_fraction,
                )
        else:
            # Need at least sustain_k passes to keep recording
            n_fail = n_total - n_pass
            if n_fail >= self.config.release_k:
                self.triggered = False
                log.debug(
                    "FrameSmoother: RELEASE (%.0f%% of window passed)",
                    100 * vote_fraction,
                )

        return SmootherResult(
            triggered      = self.triggered,
            smoothed_score = smoothed,
            raw_score      = score,
        )

    @property
    def vote_fraction(self) -> float:
        """Fraction of frames in the current window that passed."""
        if not self._buffer:
            return 0.0
        return sum(self._buffer) / len(self._buffer)

    @property
    def window_fill(self) -> float:
        """How full the window is (0–1).  < 1 during the startup period."""
        return len(self._buffer) / self.config.window_size


# ---------------------------------------------------------------------------
# ScoreSmoother — exponential moving average with separate attack/release
# ---------------------------------------------------------------------------

@dataclass
class ScoreSmootherConfig:
    """
    Parameters for the EMA score smoother.

    attack_tc   Time constant for rising scores (seconds).
                Short attack → responds quickly to song onset.
    release_tc  Time constant for falling scores (seconds).
                Long release → holds detection through brief gaps between
                syllables.
    threshold   Smoothed score above which we are triggered.
    chunk_dur   Duration of one audio chunk in seconds (used to convert
                time constants to per-frame alpha values).
    """
    attack_tc:  float = 0.15    # 150 ms attack
    release_tc: float = 0.50    # 500 ms release
    threshold:  float = 0.40
    chunk_dur:  float = 0.10    # 100 ms chunks

    @property
    def alpha_attack(self) -> float:
        """EMA alpha for rising scores (higher = faster response)."""
        return 1.0 - np.exp(-self.chunk_dur / self.attack_tc)

    @property
    def alpha_release(self) -> float:
        """EMA alpha for falling scores (lower = slower decay)."""
        return 1.0 - np.exp(-self.chunk_dur / self.release_tc)

    @classmethod
    def from_config_dict(cls, cfg: dict) -> "ScoreSmootherConfig":
        d = cfg.get("score_smoother", {})
        return cls(
            attack_tc  = d.get("attack_tc",  cls.attack_tc),
            release_tc = d.get("release_tc", cls.release_tc),
            threshold  = d.get("threshold",  cls.threshold),
            chunk_dur  = cfg.get("chunk_duration", cls.chunk_dur),
        )


class ScoreSmoother:
    """
    Exponential moving average with asymmetric attack / release.

    This is the smoother intended for use with a future CNN classifier
    confidence score. It naturally handles the inter-syllable gaps in
    birdsong: the score rises quickly when a syllable starts (short
    attack) and decays slowly through the gap until the next syllable
    arrives (long release).

    Usage
    -----
        smoother = ScoreSmoother()
        result = smoother.update(confidence)
        if result.triggered:
            record(chunk)
    """

    def __init__(self, config: ScoreSmootherConfig | None = None):
        self.config = config or ScoreSmootherConfig()
        self._ema: float = 0.0
        self.triggered: bool = False

    def reset(self) -> None:
        self._ema = 0.0
        self.triggered = False

    def update(self, score: float) -> SmootherResult:
        """
        Update with a new raw confidence score.

        Parameters
        ----------
        score : float   Raw confidence score in [0, 1] (from a future
                        classifier, or the gate score for testing).
        """
        score = float(np.clip(score, 0.0, 1.0))
        alpha = (
            self.config.alpha_attack
            if score > self._ema
            else self.config.alpha_release
        )
        self._ema = alpha * score + (1.0 - alpha) * self._ema
        self.triggered = self._ema >= self.config.threshold

        return SmootherResult(
            triggered      = self.triggered,
            smoothed_score = self._ema,
            raw_score      = score,
        )

    @property
    def ema(self) -> float:
        return self._ema


# ---------------------------------------------------------------------------
# Combined smoother: gate votes feed FrameSmoother, a future CNN classifier
# would feed ScoreSmoother
# ---------------------------------------------------------------------------

class CombinedSmoother:
    """
    Wraps both smoothers.  The gate votes go into FrameSmoother; a future
    classifier's confidence would go into ScoreSmoother.

    When only the gate is active (current state), triggered =
    frame_smoother.triggered. If a classifier stage is ever added, both
    would need to agree (AND logic) once activated.

    Parameters
    ----------
    frame_cfg  : FrameSmootherConfig or None
    score_cfg  : ScoreSmootherConfig or None
    cnn_active : bool   False while there is no classifier stage.
    """

    def __init__(
        self,
        frame_cfg:  FrameSmootherConfig  | None = None,
        score_cfg:  ScoreSmootherConfig  | None = None,
        cnn_active: bool = False,
    ):
        self.frame   = FrameSmoother(frame_cfg)
        self.score   = ScoreSmoother(score_cfg)
        self.cnn_active = cnn_active

    def reset(self) -> None:
        self.frame.reset()
        self.score.reset()

    def update_gate(self, passed: bool, gate_score: float) -> SmootherResult:
        """Call this on every chunk with the gate result."""
        return self.frame.update(passed, gate_score)

    def update_cnn(self, confidence: float) -> SmootherResult:
        """Call this on chunks that passed the gate, once a classifier
        stage is active."""
        return self.score.update(confidence)

    @property
    def triggered(self) -> bool:
        """
        Final detection decision.

        Gate-only mode        : frame smoother decides
        Gate + classifier mode: both must agree (AND logic)
        """
        if not self.cnn_active:
            return self.frame.triggered
        return self.frame.triggered and self.score.triggered

    def activate_cnn(self) -> None:
        """Call once a future CNN classifier is loaded and ready."""
        self.cnn_active = True
        log.info("CombinedSmoother: classifier stage activated")

    @classmethod
    def from_config_dict(cls, cfg: dict, cnn_active: bool = False) -> "CombinedSmoother":
        return cls(
            frame_cfg  = FrameSmootherConfig.from_config_dict(cfg),
            score_cfg  = ScoreSmootherConfig.from_config_dict(cfg),
            cnn_active = cnn_active,
        )


# ---------------------------------------------------------------------------
# Self-test (run directly: python -m pyoperant.song_recording.smoother)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== FrameSmoother test ===\n")
    fs = FrameSmoother(FrameSmootherConfig(window_size=10, onset_k=6, sustain_k=4))

    # Simulate: 12 frames of noise, then 15 frames of song, then 8 noise
    sequence = (
        [(False, 0.1)] * 12 +
        [(True,  0.8)] * 15 +
        [(False, 0.1)] * 8
    )

    prev_trig = False
    for i, (passed, score) in enumerate(sequence):
        r = fs.update(passed, score)
        if r.triggered != prev_trig:
            event = "ONSET" if r.triggered else "RELEASE"
            print(f"  Frame {i:>3}: {event}  "
                  f"(vote={fs.vote_fraction:.1%}, score={r.smoothed_score:.2f})")
        prev_trig = r.triggered

    print(f"\n  Final state: triggered={fs.triggered}, "
          f"vote={fs.vote_fraction:.1%}")

    print("\n=== ScoreSmoother test ===\n")
    ss = ScoreSmoother(ScoreSmootherConfig(
        attack_tc=0.15, release_tc=0.50, threshold=0.40, chunk_dur=0.10
    ))

    print(f"  alpha_attack={ss.config.alpha_attack:.3f}  "
          f"alpha_release={ss.config.alpha_release:.3f}")

    # Simulate syllable bursts with gaps
    syllable_pattern = (
        [0.0] * 5 +     # silence
        [0.9] * 4 +     # syllable 1
        [0.1] * 3 +     # short gap
        [0.85] * 4 +    # syllable 2
        [0.1] * 3 +     # short gap
        [0.8] * 4 +     # syllable 3
        [0.0] * 8       # end
    )

    prev_trig = False
    for i, raw in enumerate(syllable_pattern):
        r = ss.update(raw)
        if r.triggered != prev_trig:
            event = "ONSET" if r.triggered else "RELEASE"
            print(f"  Frame {i:>3}: {event}  "
                  f"(raw={raw:.2f}, ema={ss.ema:.3f})")
        prev_trig = r.triggered

    print(f"\n  Final EMA: {ss.ema:.4f}")

    print("\n=== CombinedSmoother (gate-only mode) test ===\n")
    cs = CombinedSmoother(cnn_active=False)
    for i, (passed, score) in enumerate(sequence[:20]):
        cs.update_gate(passed, score)
        if i in (5, 10, 15, 19):
            print(f"  Frame {i}: frame_triggered={cs.frame.triggered}  "
                  f"combined={cs.triggered}")
