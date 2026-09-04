"""
_pcm.py — shared PCM decode helper for song_recording's capture-layer
modules (monitor.py, noise_model.py).

pyoperant.interfaces.pyaudio_.PyAudioInterface._open_input_stream() probes
sample formats rather than assuming one (see its docstring for why 24-bit
in particular can't be assumed for a USB Audio Class device), so the
capture loops need to decode whichever format actually got negotiated --
not part of the public song_recording API, hence the leading underscore.
"""

from __future__ import annotations

import numpy as np
import pyaudio

# Full-scale magnitude for each integer PCM format PyAudio may hand back,
# used to normalise into [-1.0, 1.0] float32 -- matches each format's
# signed integer range. paInt24 is handled separately (see _decode_int24)
# since numpy has no native 24-bit dtype.
_FULL_SCALE = {
    pyaudio.paInt16: 32768.0,
    pyaudio.paInt32: 2147483648.0,
}


def decode_pcm(raw: bytes, sample_format: int, channels: int) -> np.ndarray:
    """Decode one chunk of raw PyAudio input bytes into mono float32 in
    [-1, 1], for whichever sample_format
    PyAudioInterface._open_input_stream negotiated.

    Multi-channel input is downmixed to mono by averaging channels -- cheap
    and sufficient here, since detection only needs one representative
    signal, not stereo separation.
    """
    if sample_format == pyaudio.paInt24:
        data = _decode_int24(raw)
        scale = 8388608.0  # 2**23, signed 24-bit full scale
    elif sample_format in _FULL_SCALE:
        dtype = np.int16 if sample_format == pyaudio.paInt16 else np.int32
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        scale = _FULL_SCALE[sample_format]
    else:
        raise ValueError('unsupported PyAudio sample format: %r' % (sample_format,))

    data = data / scale
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data.astype(np.float32)


def _decode_int24(raw: bytes) -> np.ndarray:
    """PyAudio's paInt24 is packed 3-byte little-endian signed samples --
    numpy has no native 24-bit dtype, so unpack by hand: pad each 3-byte
    sample to 4 bytes (sign-extending from the top/most-significant byte)
    and view the result as little-endian int32."""
    n_samples = len(raw) // 3
    buf = np.frombuffer(raw, dtype=np.uint8)[: n_samples * 3].reshape(n_samples, 3)
    padded = np.zeros((n_samples, 4), dtype=np.uint8)
    padded[:, :3] = buf
    negative = (buf[:, 2] & 0x80).astype(bool)
    padded[negative, 3] = 0xFF
    return padded.view('<i4').reshape(-1).astype(np.float32)
