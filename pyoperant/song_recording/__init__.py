# -*- coding: utf-8 -*-
"""
pyoperant.song_recording — passive vocalization detection and recording.

Detection pipeline: features.py (acoustic feature extraction) -> gate.py
(multi-feature spectral gate, optionally backed by an adaptive per-chamber
noise floor from noise_model.py) -> smoother.py (temporal smoothing of the
gate's frame-by-frame decisions) -> monitor.py (SongMonitor, the capture
loop that ties it all together and saves clips).

Runs embedded in pyoperant via pyoperant.behavior.lights.Lights, using a
panel's microphone (a pyoperant.hwio.AudioInput, typically over
pyoperant.interfaces.pyaudio_.PyAudioInterface) -- see lights.py's
song_recording config block for the integration point.

This is part of the public pyoperant repository. Defaults throughout this
subpackage are kept domain-generic (reasonable for songbird vocalizations
broadly) rather than tuned to any particular lab's chambers, species, or
hardware; anything actually specific to a deployment -- device names,
calibration data, subject data -- belongs in a bird's own config.json
(never committed to any repo), not here.
"""
