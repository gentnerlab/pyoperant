# -*- coding: utf-8 -*-
"""
Tier 1: import every pyoperant/behavior/*.py module standalone, with
hardware modules stubbed out. Catches import-time bugs (missing
dependencies, broken imports) that Tier 0 (syntax) can't, without needing
real GPIO/serial/audio hardware.

Unlike py-behaviors' Tier 1 (which loads each file via importlib.util.
spec_from_file_location to bypass glab_behaviors/__init__.py's eager
imports), these files are already real submodules of the installed
pyoperant package, so plain importlib.import_module() works directly.
"""

import importlib
import sys
import unittest
from unittest.mock import MagicMock

_HARDWARE_MODULES = ["serial", "pyaudio", "pigpio", "comedi", "RPi", "RPi.GPIO", "smbus2", "hx711"]

_BEHAVIOR_MODULES = [
    "pyoperant.behavior.base",
    "pyoperant.behavior.lights",
    "pyoperant.behavior.shape",
    "pyoperant.behavior.two_alt_choice",
    "pyoperant.behavior.two_alt_choice_early_responses",
    "pyoperant.behavior.place_pref_24hr",
    "pyoperant.behavior.three_ac_matching",
]

_SONG_RECORDING_MODULES = [
    "pyoperant.song_recording",
    "pyoperant.song_recording._pcm",
    "pyoperant.song_recording.calibration",
    "pyoperant.song_recording.features",
    "pyoperant.song_recording.gate",
    "pyoperant.song_recording.smoother",
    "pyoperant.song_recording.variability",
    "pyoperant.song_recording.noise_model",
    "pyoperant.song_recording.monitor",
    "pyoperant.song_recording.melspec",
    "pyoperant.song_recording.cnn_numpy",
    "pyoperant.song_recording.classifier",
]


def _stub_hardware_modules():
    for name in _HARDWARE_MODULES:
        if name not in sys.modules:
            try:
                importlib.import_module(name)
            except ImportError:
                sys.modules[name] = MagicMock()


class TestBehaviorImports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _stub_hardware_modules()


def _make_test(modname):
    def test(self):
        try:
            importlib.import_module(modname)
        except Exception as e:
            self.fail("{} fails to import under Python 3: {}: {}".format(
                modname, type(e).__name__, e))

    return test


for _modname in _BEHAVIOR_MODULES:
    _test_name = "test_" + _modname.replace(".", "_")
    setattr(TestBehaviorImports, _test_name, _make_test(_modname))


class TestSongRecordingImports(unittest.TestCase):
    """pyaudio is stubbed the same way as for TestBehaviorImports above --
    song_recording's capture layer (monitor.py, noise_model.py via _pcm.py)
    imports pyaudio for its format constants, but none of these modules
    need real audio hardware just to import."""
    @classmethod
    def setUpClass(cls):
        _stub_hardware_modules()


for _modname in _SONG_RECORDING_MODULES:
    _test_name = "test_" + _modname.replace(".", "_")
    setattr(TestSongRecordingImports, _test_name, _make_test(_modname))


if __name__ == "__main__":
    unittest.main()
