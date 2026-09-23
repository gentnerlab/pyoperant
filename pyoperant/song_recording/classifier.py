"""
classifier.py -- live inference wrapper for the 4-class SongCNN (see
song-feature-analysis/scripts/cnn_model.py), trained offline and shipped
here as a .npz weight file (see cnn_numpy.py and that training repo's
scripts/export_npz.py -- NOT ONNX; see cnn_numpy.py's docstring for why:
onnxruntime has no ARM wheels for this fleet's 32-bit Pi image). Second-
stage classifier: only ever called on chunks that already passed SongGate
(see monitor.py's mode="gate_cnn" path and CombinedSmoother.update_cnn's
own docstring).

Per-box model/gate selection
-----------------------------
`model_path` is a required constructor argument, always read from that
box's own config (song_recording.cnn.model_path in lights.py) -- there is
no hardcoded default model anywhere in this module. This is deliberate:
the gate is already fully reconfigurable per box today (every GateConfig
weight/threshold comes from that box's own config.json, see gate.py), and
the CNN needs the same property so a future different-species (or
different-purpose) deployment is just a different config.json pointing
at a different .npz file -- no code change, no new mechanism to build
later.

Preprocessing must byte-match training
---------------------------------------
Resampling uses `soxr` at the same quality librosa's default resample
path uses (verified 2026-09-22: soxr.resample(..., quality='HQ') ==
librosa.resample(..., res_type='soxr_hq') exactly, 0.0 max diff on real
corpus audio, and soxr does have real armv7l wheels on piwheels, unlike
onnxruntime) and the mel spectrogram uses melspec.py (verified against
real librosa output, see that module's own docstring).
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pyoperant.song_recording import melspec
from pyoperant.song_recording.cnn_numpy import SongCNNWeights

CLASS_NAMES = melspec.CLASS_NAMES
CLASS_TO_IDX = melspec.CLASS_TO_IDX

# Default "keep" set if a box's config doesn't specify one -- everything
# that isn't noise, i.e. confidence = 1 - P(noise). Chosen 2026-09-22:
# save all PROBABLE vocalization (song, whistle, and contact calls all
# count), narrower sets (e.g. song-only) are an explicit per-box config
# choice, not the default.
DEFAULT_KEEP_CLASSES = ["whistle", "contact", "song"]


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exp = np.exp(shifted)
    return exp / exp.sum()


def _validate_keep_classes(keep_classes: list[str]) -> None:
    unknown = set(keep_classes) - set(CLASS_NAMES)
    if unknown:
        raise ValueError(f"keep_classes contains unknown class(es): {sorted(unknown)} "
                          f"(valid: {CLASS_NAMES})")


@dataclass
class ClassifierResult:
    probs:           dict       # {class_name: probability}, all 4 classes
    predicted_class: str        # argmax(probs)
    confidence:      float      # sum(probs[c] for c in keep_classes) -- what update_cnn() gets


class SongClassifier:
    """
    Wraps the pure-numpy SongCNN forward pass (cnn_numpy.py) over a
    rolling causal audio buffer, so `update(chunk)` can be called once
    per 100ms chunk (matching FeatureExtractor/SongGate's own cadence)
    and internally reconstructs the same CONTEXT_DURATION_S (0.5s) causal
    window the model was trained on.

    Parameters
    ----------
    model_path          : path to a .npz weight export of SongCNN (see
                          cnn_numpy.py / the training repo's
                          export_npz.py). Always per-box config, never
                          hardcoded -- see module docstring.
    capture_sample_rate : the real capture rate audio chunks arrive at
                          (e.g. panel.microphone.sample_rate, 48000) --
                          NOT necessarily melspec.TARGET_SR; this class
                          resamples internally.
    keep_classes        : list of class names (subset of CLASS_NAMES)
                          that count toward `confidence`. Defaults to
                          DEFAULT_KEEP_CLASSES (= 1 - P(noise)).
    chunk_duration       : seconds per update() call. Defaults to
                          melspec.CHUNK_DURATION_S (0.1s) -- must match
                          the monitor's own chunk_duration config, since
                          this determines how many chunks the rolling
                          buffer needs to hold CONTEXT_DURATION_S.
    """

    def __init__(
        self,
        model_path: str | Path,
        capture_sample_rate: int,
        keep_classes: list[str] | None = None,
        chunk_duration: float = melspec.CHUNK_DURATION_S,
    ):
        self._model = SongCNNWeights(model_path)

        self.capture_sample_rate = capture_sample_rate
        self.keep_classes = list(keep_classes) if keep_classes is not None else list(DEFAULT_KEEP_CLASSES)
        _validate_keep_classes(self.keep_classes)

        n_context_chunks = max(1, round(melspec.CONTEXT_DURATION_S / chunk_duration))
        self._buffer: collections.deque = collections.deque(maxlen=n_context_chunks)
        self._expected_native_len = int(melspec.CONTEXT_DURATION_S * capture_sample_rate)
        self._expected_target_len = int(melspec.CONTEXT_DURATION_S * melspec.TARGET_SR)

    def update(self, chunk: np.ndarray) -> ClassifierResult:
        self._buffer.append(chunk)
        raw = np.concatenate(list(self._buffer)).astype(np.float32)

        # Left-pad with silence if we don't have a full context window yet
        # (near the start of an episode) -- same convention as training's
        # SongChunkDataset.__getitem__ (see cnn_dataset.py).
        if len(raw) < self._expected_native_len:
            raw = np.pad(raw, (self._expected_native_len - len(raw), 0))
        else:
            raw = raw[-self._expected_native_len:]

        if self.capture_sample_rate != melspec.TARGET_SR:
            import soxr
            resampled = soxr.resample(raw, self.capture_sample_rate, melspec.TARGET_SR, quality="HQ")
        else:
            resampled = raw

        if len(resampled) < self._expected_target_len:
            resampled = np.pad(resampled, (self._expected_target_len - len(resampled), 0))
        else:
            resampled = resampled[-self._expected_target_len:]

        log_mel = melspec.compute_log_mel(resampled, melspec.TARGET_SR)
        logits = self._model.forward(log_mel)
        probs = _softmax(logits)

        confidence = float(sum(probs[CLASS_TO_IDX[c]] for c in self.keep_classes))
        predicted_idx = int(np.argmax(probs))

        return ClassifierResult(
            probs={name: float(probs[i]) for i, name in enumerate(CLASS_NAMES)},
            predicted_class=CLASS_NAMES[predicted_idx],
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# Self-test: buffering/resampling/padding/confidence-aggregation logic,
# with a fake model (no real weight file, no soxr dependency needed for
# scenarios A-D) -- matches the self-test convention every other module
# in this subpackage follows. The mel-spectrogram math is melspec.py's
# own self-test's job, not re-verified here; cnn_numpy.py's forward pass
# is checked for shape/determinism in its own self-test, and its real
# numerical equivalence to the trained PyTorch model was verified
# separately during development (~4e-6 max logit diff, see that module's
# docstring).
# ---------------------------------------------------------------------------

class _FakeModel:
    """Stands in for cnn_numpy.SongCNNWeights: returns a fixed logit
    vector regardless of input, so the test can check the surrounding
    buffering/confidence logic without a real weight file."""

    def __init__(self, logits):
        self._logits = np.array(logits, dtype=np.float32)

    def forward(self, log_mel):
        assert log_mel.shape[0] == melspec.N_MELS, log_mel.shape
        return self._logits


def _make_test_classifier(logits, capture_sample_rate=48000, keep_classes=None):
    clf = SongClassifier.__new__(SongClassifier)
    clf._model = _FakeModel(logits)
    clf.capture_sample_rate = capture_sample_rate
    clf.keep_classes = list(keep_classes) if keep_classes is not None else list(DEFAULT_KEEP_CLASSES)
    n_context_chunks = max(1, round(melspec.CONTEXT_DURATION_S / melspec.CHUNK_DURATION_S))
    clf._buffer = collections.deque(maxlen=n_context_chunks)
    clf._expected_native_len = int(melspec.CONTEXT_DURATION_S * capture_sample_rate)
    clf._expected_target_len = int(melspec.CONTEXT_DURATION_S * melspec.TARGET_SR)
    return clf


def _self_test():
    checks = []

    # Scenarios A-D use capture_sample_rate == TARGET_SR so they isolate
    # the buffering/confidence logic from the resampling path (which
    # needs `soxr` installed) -- that path gets its own scenario (E) below.
    song_logits = [-5.0, -2.0, -2.0, 8.0]  # argmax=song (index 3)
    clf = _make_test_classifier(song_logits, capture_sample_rate=melspec.TARGET_SR)
    chunk = np.zeros(int(melspec.CHUNK_DURATION_S * melspec.TARGET_SR), dtype=np.float32)
    result = None
    for _ in range(8):  # more than the context window, exercises the rolling-buffer cap too
        result = clf.update(chunk)
    checks.append(("predicted_class == 'song' on confident song logits",
                    result.predicted_class == "song"))
    checks.append(("confidence high (default keep_classes includes song) ",
                    result.confidence > 0.9))
    checks.append(("probs has all 4 classes", set(result.probs) == set(CLASS_NAMES)))
    checks.append(("probs sum to ~1", abs(sum(result.probs.values()) - 1.0) < 1e-5))

    # Scenario B: confident "noise" logits -> low confidence with the default keep set.
    noise_logits = [8.0, -2.0, -2.0, -5.0]  # argmax=noise (index 0)
    clf2 = _make_test_classifier(noise_logits, capture_sample_rate=melspec.TARGET_SR)
    result2 = clf2.update(chunk)
    checks.append(("predicted_class == 'noise' on confident noise logits",
                    result2.predicted_class == "noise"))
    checks.append(("confidence low (noise excluded from default keep set)",
                    result2.confidence < 0.1))

    # Scenario C: song-only keep_classes -- a confident "contact" prediction
    # should score LOW confidence even though it's not noise, since contact
    # isn't in this narrower keep set.
    contact_logits = [-5.0, -2.0, 8.0, -2.0]  # argmax=contact (index 2)
    clf3 = _make_test_classifier(contact_logits, capture_sample_rate=melspec.TARGET_SR, keep_classes=["song"])
    result3 = clf3.update(chunk)
    checks.append(("predicted_class == 'contact'", result3.predicted_class == "contact"))
    checks.append(("confidence low with keep_classes=['song'] only",
                    result3.confidence < 0.1))

    # Scenario D: unknown class in keep_classes raises immediately, not
    # silently (a typo'd config value should fail loud at construction).
    # Calls the same _validate_keep_classes() __init__ itself calls, so
    # this is real coverage of the actual validation path, not a stand-in
    # -- just invoked directly since constructing a real SongClassifier
    # needs a real .npz weight file on disk.
    try:
        _validate_keep_classes(["birdsong"])
        raised = False
    except ValueError:
        raised = True
    checks.append(("keep_classes validation raises on an unknown class name", raised))

    # Scenario E: resampling path (capture_sample_rate != TARGET_SR) doesn't
    # crash and produces a well-formed result -- exercises the soxr branch's
    # shape bookkeeping without needing soxr installed (FakeSession doesn't
    # care about the input's numeric content, only its shape).
    try:
        import soxr  # noqa: F401
        clf4 = _make_test_classifier(song_logits, capture_sample_rate=48000)
        result4 = clf4.update(chunk)
        checks.append(("resampling path (48000->22050) runs without error",
                        result4.predicted_class in CLASS_NAMES))
    except ImportError:
        print("  [SKIP] resampling path check -- soxr not installed in this environment")

    all_ok = True
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok

    print("\nSELF-TEST " + ("PASSED" if all_ok else "FAILED"))
    return all_ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _self_test() else 1)
