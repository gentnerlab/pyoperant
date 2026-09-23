"""
melspec.py -- pure numpy/scipy log-mel spectrogram, byte-matched to
librosa.feature.melspectrogram + librosa.power_to_db at the exact
parameters the CNN classifier (see classifier.py) was trained with.

Why this exists instead of just calling librosa: this module runs on the
Pi, where `librosa` would be a heavy dependency to cross-compile/install
offline (numba, llvmlite, audioread, ...) for no benefit -- the training
side (song-feature-analysis/scripts/cnn_dataset.py) already reduces to a
short, well-defined mel filterbank + STFT + power-to-dB pipeline that's
cheap to port directly to numpy/scipy. Verified 2026-09-22 against real
librosa output on real corpus audio across multiple files: max abs diff
~1e-5 (float32 precision noise, not a real discrepancy).

**Keep these constants and the pipeline itself in exact sync with
cnn_dataset.py** -- this is a deliberate duplication (the Pi can't import
the training repo), not shared code, so a change on the training side
(TARGET_SR, N_MELS, N_FFT, HOP_LENGTH, or the mel/dB math itself) must be
ported here by hand or live inference silently drifts from what the model
was actually trained on -- the worst kind of bug, since it degrades
accuracy with no obvious error.

librosa version this was verified against: 1.0.0. Two version-specific
details that are NOT numpy/scipy universal defaults and would silently
break the match if librosa's own defaults ever change:
  - STFT center-padding uses pad_mode='constant' (zero-padding), not
    'reflect' -- reflect was librosa's default in older versions.
  - The mel filterbank uses the Slaney mel scale + Slaney-style area
    normalization (librosa's htk=False, norm='slaney' defaults).
"""

from __future__ import annotations

import numpy as np
from scipy.signal.windows import hann as _scipy_hann

# Must match song-feature-analysis/scripts/cnn_dataset.py exactly -- see
# module docstring.
TARGET_SR = 22050
N_MELS = 40
N_FFT = 1024
HOP_LENGTH = 256
CONTEXT_DURATION_S = 0.5
CHUNK_DURATION_S = 0.1

CLASS_NAMES = ["noise", "whistle", "contact", "song"]
CLASS_TO_IDX = {name: i for i, name in enumerate(CLASS_NAMES)}


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    """Slaney mel scale (librosa's htk=False default)."""
    hz = np.asarray(hz, dtype=np.float64)
    f_min, f_sp = 0.0, 200.0 / 3
    mel = (hz - f_min) / f_sp
    min_log_hz = 1000.0
    min_log_mel = (min_log_hz - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    log_region = hz >= min_log_hz
    return np.where(
        log_region,
        min_log_mel + np.log(np.maximum(hz, 1e-10) / min_log_hz) / logstep,
        mel,
    )


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    mel = np.asarray(mel, dtype=np.float64)
    f_min, f_sp = 0.0, 200.0 / 3
    hz = f_min + f_sp * mel
    min_log_hz = 1000.0
    min_log_mel = (min_log_hz - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    log_region = mel >= min_log_mel
    return np.where(log_region, min_log_hz * np.exp(logstep * (mel - min_log_mel)), hz)


def _mel_filterbank(sr: int, n_fft: int, n_mels: int, fmin: float = 0.0,
                     fmax: float | None = None) -> np.ndarray:
    """Slaney-normalized triangular mel filterbank -- see module
    docstring. Shape (n_mels, n_fft // 2 + 1)."""
    if fmax is None:
        fmax = sr / 2
    n_freqs = n_fft // 2 + 1
    fftfreqs = np.fft.rfftfreq(n=n_fft, d=1.0 / sr)

    mels = np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2)
    mel_f = _mel_to_hz(mels)
    fdiff = np.diff(mel_f)
    ramps = np.subtract.outer(mel_f, fftfreqs)

    weights = np.zeros((n_mels, n_freqs), dtype=np.float64)
    for i in range(n_mels):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        weights[i] = np.maximum(0, np.minimum(lower, upper))

    # Slaney-style area normalization (librosa's norm='slaney' default).
    enorm = 2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels])
    weights *= enorm[:, np.newaxis]
    return weights.astype(np.float32)


_MEL_FB = _mel_filterbank(TARGET_SR, N_FFT, N_MELS, fmin=0.0, fmax=TARGET_SR / 2)
_HANN = _scipy_hann(N_FFT, sym=False)  # periodic Hann, matches librosa's default window


def compute_log_mel(y: np.ndarray, sr: int = TARGET_SR) -> np.ndarray:
    """log-mel spectrogram, shape (N_MELS, n_frames) -- byte-matched to
    librosa.feature.melspectrogram(y, sr, n_fft=N_FFT,
    hop_length=HOP_LENGTH, n_mels=N_MELS, fmin=0, fmax=sr/2) followed by
    librosa.power_to_db(mel, ref=np.max). `sr` must be TARGET_SR -- this
    function does not resample (see classifier.py, which resamples the
    live capture rate down to TARGET_SR via soxr before calling this)."""
    y = np.asarray(y, dtype=np.float64)

    pad = N_FFT // 2
    y_padded = np.pad(y, pad, mode="constant")  # zero-pad -- see module docstring
    n_frames = 1 + (len(y_padded) - N_FFT) // HOP_LENGTH
    frames = np.lib.stride_tricks.as_strided(
        y_padded,
        shape=(N_FFT, n_frames),
        strides=(y_padded.strides[0], y_padded.strides[0] * HOP_LENGTH),
    )
    windowed = frames * _HANN[:, None]
    spec = np.fft.rfft(windowed, axis=0)
    power = np.abs(spec) ** 2
    mel_power = _MEL_FB.astype(np.float64) @ power

    amin = 1e-10
    ref = np.max(mel_power)
    log_spec = 10.0 * np.log10(np.maximum(amin, mel_power))
    log_spec -= 10.0 * np.log10(np.maximum(amin, ref))
    top_db = 80.0
    log_spec = np.maximum(log_spec, log_spec.max() - top_db)
    return log_spec.astype(np.float32)


# ---------------------------------------------------------------------------
# Self-test: a synthetic signal + its expected output, both computed once
# with real librosa (song-feature-analysis env, librosa 1.0.0) and
# hardcoded here so this module's own self-test needs no librosa/soxr/
# training-repo dependency at all -- just numpy/scipy, same as production.
# ---------------------------------------------------------------------------

def _self_test():
    rng = np.random.default_rng(42)
    t = np.arange(int(CONTEXT_DURATION_S * TARGET_SR)) / TARGET_SR
    y = (0.5 * np.sin(2 * np.pi * 1500 * t)
         + 0.3 * np.sin(2 * np.pi * 3200 * t)
         + 0.05 * rng.standard_normal(len(t))).astype(np.float32)

    mel = compute_log_mel(y, TARGET_SR)
    expected_shape = (N_MELS, 44)
    expected_checksum = -58021.1953125
    expected_first_row_head = [-30.64041519165039, -34.54918670654297,
                                -38.81706237792969, -36.99931335449219,
                                -37.500606536865234]

    checks = [
        ("shape matches (40, 44)", mel.shape == expected_shape),
        ("checksum matches librosa reference (atol=1e-2)",
         abs(float(mel.sum()) - expected_checksum) < 1e-2),
        ("first row head matches librosa reference (atol=1e-3)",
         np.allclose(mel[0, :5], expected_first_row_head, atol=1e-3)),
    ]
    all_ok = True
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok

    print("\nSELF-TEST " + ("PASSED" if all_ok else "FAILED"))
    return all_ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _self_test() else 1)
