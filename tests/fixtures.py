# -*- coding: utf-8 -*-
"""
Shared fixtures for the Tier 2 instantiation/trial-stepping tests
(test_instantiate.py). Not a test module itself -- no tests in here.

Mirrors the fixtures built for py-behaviors' tests/ -- see that repo's
tests/fixtures.py for the sibling implementation.
"""

import datetime as dt
import os
import struct
import wave

from pyoperant import panels


class FakePort(object):
    """Stands in for a pyoperant peck-port component (left/center/right).

    status() returns True immediately (rather than waiting for a real beam
    break) so response_main()'s polling loop in two_alt_choice.py resolves
    on its first pass instead of looping in real time.
    """

    def __init__(self, name):
        self.name = name
        self.calls = []

    def on(self):
        self.calls.append("on")

    def off(self):
        self.calls.append("off")

    def poll(self, timeout=None):
        self.calls.append("poll")
        return dt.datetime.now()

    def status(self):
        self.calls.append("status")
        return True

    def flash(self, dur=1.0):
        self.calls.append("flash")
        return dt.datetime.now()


class FakeLight(object):
    def __init__(self):
        self.calls = []

    def on(self):
        self.calls.append("on")

    def off(self):
        self.calls.append("off")


class FakeSpeaker(object):
    def __init__(self):
        self.calls = []

    def queue(self, path):
        self.calls.append(("queue", path))

    def play(self):
        self.calls.append("play")

    def stop(self):
        self.calls.append("stop")


class FakeCue(object):
    def __init__(self):
        self.calls = []

    def red(self):
        self.calls.append("red")

    def green(self):
        self.calls.append("green")

    def blue(self):
        self.calls.append("blue")

    def off(self):
        self.calls.append("off")


class FakePanel(panels.BasePanel):
    """Minimal stand-in for a real hardware Panel -- enough to satisfy
    BaseExp/TwoAltChoiceExp/Shaper without touching any GPIO/serial/audio
    hardware. Subclasses panels.BasePanel because shape.Shaper.__init__
    asserts isinstance(panel, panels.BasePanel)."""

    def __init__(self):
        super(FakePanel, self).__init__()
        self.house_light = FakeLight()
        self.left = FakePort("left")
        self.center = FakePort("center")
        self.right = FakePort("right")
        self.speaker = FakeSpeaker()
        self.cue = FakeCue()
        self.reset_calls = 0
        self.reward_calls = []
        self.punish_calls = []

    def reset(self):
        self.reset_calls += 1
        return True

    def reward(self, value=1.0):
        self.reward_calls.append(value)
        return dt.datetime.now()

    def punish(self, value=1.0):
        self.punish_calls.append(value)
        return dt.datetime.now()


def make_dummy_wav(path, duration=0.05, framerate=44100):
    """Writes a minimal valid, silent 16-bit mono PCM wav file. Real
    behaviors read stim durations via wave.open() (pyoperant.utils.
    auditory_stim_from_wav), so a well-formed but silent file is enough."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nframes = int(duration * framerate)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(struct.pack("<%dh" % nframes, *([0] * nframes)))


def prepare_experiment_dirs(config, tmp_dir):
    """Returns a deep copy of config with experiment_path/stim_path
    redirected under tmp_dir, with both directories created on disk."""
    import copy

    config = copy.deepcopy(config)
    experiment_path = os.path.join(tmp_dir, "experiment")
    stim_path = os.path.join(tmp_dir, "stims")
    os.makedirs(experiment_path, exist_ok=True)
    os.makedirs(stim_path, exist_ok=True)
    config["experiment_path"] = experiment_path
    config["stim_path"] = stim_path
    return config


def make_dummy_wavs_for_config_stims(config, stim_key="stims", path_key="stim_path"):
    """Pre-create dummy wavs for a raw config[stim_key] dict (relative
    filenames, joined with config[path_key] the same way TwoAltChoiceExp.
    __init__ does) so construction doesn't fail on a missing input file."""
    stim_path = config.get(path_key, "")
    for filename in config.get(stim_key, {}).values():
        path = filename if os.path.isabs(filename) else os.path.join(stim_path, filename)
        if not os.path.exists(path):
            make_dummy_wav(path)


def make_dummy_wavs_for_stims(parameters, stim_keys=("stims",)):
    """After a Behavior's __init__ has populated one or more parameters[key]
    dicts with real file paths, write a silent dummy wav at each unique path
    so get_stimuli()/prep_stimuli() -> auditory_stim_from_wav() can read a
    real duration."""
    seen = set()
    for key in stim_keys:
        for path in parameters.get(key, {}).values():
            if path in seen:
                continue
            seen.add(path)
            if not os.path.exists(path):
                make_dummy_wav(path)
