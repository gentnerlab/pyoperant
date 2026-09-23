"""
cnn_numpy.py -- pure numpy forward pass for SongCNN (see
song-feature-analysis/scripts/cnn_model.py), loading weights from a plain
.npz file exported from a trained PyTorch checkpoint (see that repo's
scripts/export_npz.py).

Why not onnxruntime: checked 2026-09-22 -- the fleet's Pi image is
32-bit ARM (armv7/armhf, see rpioperant/magpi/download_packages.sh's
`--platform linux/arm/v7` build target), and onnxruntime has ZERO
successful armv7 wheel builds on piwheels.org (the project's only
realistic source of prebuilt wheels for this platform; building it from
source is a multi-hour C++/CMake/protobuf undertaking, not something to
add to an offline package pipeline). SongCNN is tiny (25,732 parameters,
3 conv blocks) -- small enough that a direct numpy port is genuinely
simpler and more robust than chasing a runtime dependency this platform
doesn't have prebuilt wheels for, and it removes the dependency risk
entirely rather than trading it for a different fragile one.

Verified 2026-09-22 against the real trained PyTorch model on real
extracted log-mel inputs: max abs logit diff ~1e-5 (float32 precision
noise, not a real discrepancy). ONNX export stays in the training repo's
train_cnn.py anyway -- useful for desktop tooling/other platforms, just
not what ships to a box.

**Architecture must stay in exact sync with
song-feature-analysis/scripts/cnn_model.py** -- this is a deliberate
duplication (same reasoning as melspec.py's own docstring), not shared
code. A change to SongCNN's topology (layer sizes, added/removed layers)
must be ported here by hand, and export_npz.py's key names must keep
matching this module's expectations.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

BN_EPS = 1e-5  # PyTorch's nn.BatchNorm2d default


def _conv2d(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    """3x3 conv, stride 1, padding 1 (matches SongCNN's only conv config).
    x: (C_in, H, W). weight: (C_out, C_in, 3, 3). bias: (C_out,).
    Returns (C_out, H, W) -- same spatial size (padding=1 preserves it).
    """
    c_in, h, w = x.shape
    c_out = weight.shape[0]
    x_padded = np.pad(x, ((0, 0), (1, 1), (1, 1)))

    # im2col via sliding_window_view: stack every 3x3 patch position into
    # columns, then one matmul -- much faster than a naive 4-nested-loop
    # convolution. First cut of this used a Python-level triple loop (over
    # c_in x 3 x 3 = up to 288 iterations for this model's largest conv)
    # to build the same matrix; measured on real Pi hardware (2026-09-22,
    # magpi06) that loop alone cost ~22-23ms per call on the two biggest
    # conv layers -- real budget against the 100ms/chunk real-time
    # requirement (a full gate+CNN chunk was 78.9ms, only ~21ms of
    # margin). sliding_window_view gives the same (c_in, 3, 3, H, W)
    # patch stack with zero Python-level looping. windows: (c_in, H, W,
    # kh, kw) -- transpose to (c_in, kh, kw, H, W) to match weight's own
    # (C_out, C_in, kh, kw) flattening order before the reshape below.
    windows = np.lib.stride_tricks.sliding_window_view(x_padded, (3, 3), axis=(1, 2))
    cols = windows.transpose(0, 3, 4, 1, 2).reshape(c_in * 9, h * w).astype(np.float64)

    w_mat = weight.reshape(c_out, -1).astype(np.float64)
    out = w_mat @ cols + bias.astype(np.float64)[:, None]
    return out.reshape(c_out, h, w)


def _batchnorm2d(x: np.ndarray, weight, bias, running_mean, running_var) -> np.ndarray:
    """Eval-mode BatchNorm2d: uses running stats, not batch stats (there
    is no "batch" at inference time -- one chunk at a time)."""
    mean = running_mean.astype(np.float64)[:, None, None]
    var  = running_var.astype(np.float64)[:, None, None]
    w    = weight.astype(np.float64)[:, None, None]
    b    = bias.astype(np.float64)[:, None, None]
    return (x - mean) / np.sqrt(var + BN_EPS) * w + b


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def _maxpool2d_2(x: np.ndarray) -> np.ndarray:
    """2x2 max pool, stride 2. Assumes even H, W (true throughout
    SongCNN's fixed 40x44 input -> 20x22 -> 10x11)."""
    c, h, w = x.shape
    return x.reshape(c, h // 2, 2, w // 2, 2).max(axis=(2, 4))


def _global_avg_pool(x: np.ndarray) -> np.ndarray:
    """AdaptiveAvgPool2d(1) -> a plain per-channel mean. Returns (C,)."""
    return x.mean(axis=(1, 2))


def _linear(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    return weight.astype(np.float64) @ x + bias.astype(np.float64)


class SongCNNWeights:
    """Loads and holds a SongCNN checkpoint's weights (from export_npz.py's
    .npz format). `forward()` is dropout-free (eval mode -- dropout is a
    training-only regularizer, a no-op at inference)."""

    def __init__(self, npz_path: str | Path):
        data = np.load(str(npz_path))
        self.w = {k: data[k] for k in data.files}

    def forward(self, log_mel: np.ndarray) -> np.ndarray:
        """log_mel: (n_mels, n_frames), e.g. (40, 44). Returns raw logits,
        shape (4,) -- apply softmax yourself, matching cnn_model.py's own
        contract (composes with CrossEntropyLoss during training, so the
        exported/ported forward pass stays logits, not probabilities)."""
        w = self.w
        x = log_mel[np.newaxis, :, :].astype(np.float64)  # (1, n_mels, n_frames) -- 1 "channel"

        x = _conv2d(x, w["conv1_weight"], w["conv1_bias"])
        x = _batchnorm2d(x, w["bn1_weight"], w["bn1_bias"], w["bn1_running_mean"], w["bn1_running_var"])
        x = _relu(x)
        x = _maxpool2d_2(x)

        x = _conv2d(x, w["conv2_weight"], w["conv2_bias"])
        x = _batchnorm2d(x, w["bn2_weight"], w["bn2_bias"], w["bn2_running_mean"], w["bn2_running_var"])
        x = _relu(x)
        x = _maxpool2d_2(x)

        x = _conv2d(x, w["conv3_weight"], w["conv3_bias"])
        x = _batchnorm2d(x, w["bn3_weight"], w["bn3_bias"], w["bn3_running_mean"], w["bn3_running_var"])
        x = _relu(x)
        x = _global_avg_pool(x)  # (64,)

        x = _linear(x, w["fc1_weight"], w["fc1_bias"])
        x = _relu(x)
        logits = _linear(x, w["fc2_weight"], w["fc2_bias"])
        return logits.astype(np.float32)


# ---------------------------------------------------------------------------
# Self-test: architecture/shape sanity on random weights (no real
# checkpoint needed -- numerical equivalence to the real trained PyTorch
# model was verified separately, once, during development; see this
# module's docstring). Matches the self-test convention every other
# module in this subpackage follows.
# ---------------------------------------------------------------------------

def _self_test():
    rng = np.random.default_rng(7)

    def rnd(*shape):
        return rng.standard_normal(shape).astype(np.float32)

    weights = {
        "conv1_weight": rnd(16, 1, 3, 3), "conv1_bias": rnd(16),
        "bn1_weight": np.abs(rnd(16)) + 0.1, "bn1_bias": rnd(16),
        "bn1_running_mean": rnd(16), "bn1_running_var": np.abs(rnd(16)) + 0.1,

        "conv2_weight": rnd(32, 16, 3, 3), "conv2_bias": rnd(32),
        "bn2_weight": np.abs(rnd(32)) + 0.1, "bn2_bias": rnd(32),
        "bn2_running_mean": rnd(32), "bn2_running_var": np.abs(rnd(32)) + 0.1,

        "conv3_weight": rnd(64, 32, 3, 3), "conv3_bias": rnd(64),
        "bn3_weight": np.abs(rnd(64)) + 0.1, "bn3_bias": rnd(64),
        "bn3_running_mean": rnd(64), "bn3_running_var": np.abs(rnd(64)) + 0.1,

        "fc1_weight": rnd(32, 64), "fc1_bias": rnd(32),
        "fc2_weight": rnd(4, 32), "fc2_bias": rnd(4),
    }
    npz_path = "/tmp/_cnn_numpy_selftest_weights.npz"
    np.savez(npz_path, **weights)

    model = SongCNNWeights(npz_path)
    log_mel = rng.standard_normal((40, 44)).astype(np.float32)
    logits = model.forward(log_mel)

    checks = [
        ("output shape is (4,)", logits.shape == (4,)),
        ("output is finite (no NaN/Inf)", np.all(np.isfinite(logits))),
        ("output dtype is float32", logits.dtype == np.float32),
    ]
    # Determinism: same input twice -> identical output (no hidden state).
    logits2 = model.forward(log_mel)
    checks.append(("deterministic (same input -> same output)", np.array_equal(logits, logits2)))

    all_ok = True
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok

    print("\nSELF-TEST " + ("PASSED" if all_ok else "FAILED"))
    print("(Numerical equivalence to the real trained PyTorch model was "
          "verified separately against a real checkpoint -- see module docstring.)")
    return all_ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _self_test() else 1)
