import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _mod in ("serial", "pyaudio", "pigpio"):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

from fixtures import FakePanel, prepare_experiment_dirs  # noqa: E402
from pyoperant.behavior import Lights  # noqa: E402
from pyoperant.song_recording import species  # noqa: E402
from pyoperant.song_recording.monitor import DetectionLog  # noqa: E402


class TestSpeciesPresets(unittest.TestCase):
    def test_defaults_to_starling_and_unknown_raises(self):
        self.assertEqual(species.resolve_species({}), "starling")
        self.assertEqual(species.resolve_species({"species": "zebra_finch"}), "zebra_finch")
        with self.assertRaises(species.UnknownSpeciesError):
            species.resolve_species({"species": "canary"})

    def test_starling_preset_changes_nothing(self):
        cfg = {"enabled": True, "gate": {"threshold": 0.5}}
        self.assertEqual(species.apply_preset("starling", cfg), cfg)

    def test_user_config_wins_over_preset(self):
        saved = species.PRESETS["zebra_finch"]
        species.PRESETS["zebra_finch"] = {"monitor": {"freq_low": 500, "freq_high": 8000}}
        try:
            merged = species.apply_preset(
                "zebra_finch", {"monitor": {"freq_high": 9000}, "enabled": True})
        finally:
            species.PRESETS["zebra_finch"] = saved
        self.assertEqual(merged["monitor"], {"freq_low": 500, "freq_high": 9000})

    def test_zebra_finch_stub_warns_and_returns_generic_gate(self):
        with self.assertLogs("pyoperant.song_recording.species", level="WARNING"):
            gate, extractor = species.make_gate(
                "zebra_finch", {"sample_rate": 48000, "gate": {}, "noise_model": {}})
        self.assertFalse(gate.has_noise_model)

    def test_gate_factory_override_is_imported_and_used(self):
        sentinel = (object(), object())
        species.GATE_FACTORIES  # noqa: B018 -- registry unchanged by override
        import tests.test_species as me
        me._FACTORY_CALLS = []

        def fake(cfg):
            me._FACTORY_CALLS.append(cfg)
            return sentinel
        me._fake_factory = fake
        got = species.make_gate("zebra_finch", {"a": 1}, "tests.test_species:_fake_factory")
        self.assertIs(got, sentinel)
        self.assertEqual(me._FACTORY_CALLS, [{"a": 1}])

    def test_bad_gate_factory_spec_raises(self):
        with self.assertRaises(ValueError):
            species.make_gate("starling", {}, "no_colon_here")


class TestLightsSpecies(unittest.TestCase):
    def _build(self, **sr):
        import json
        import os
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "example_configs", "Lights.json")
        with open(cfg_path) as f:
            config = json.load(f)
        config.pop("free_food_schedule", None)
        config["song_recording"] = dict({"enabled": True}, **sr)
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            exp = Lights(panel=FakePanel(), **config)
            exp._build_pipeline()
            return exp

    def test_default_species_is_starling(self):
        exp = self._build()
        self.assertEqual(exp._species, "starling")
        self.assertIsNotNone(exp._gate)

    def test_zebra_finch_builds_a_pipeline(self):
        exp = self._build(species="zebra_finch")
        self.assertEqual(exp._species, "zebra_finch")
        self.assertIsNotNone(exp._gate)

    def test_unknown_species_disables_recording(self):
        exp = self._build(species="canary")
        self.assertIsNone(exp._gate)
        self.assertIsNone(exp._smoother)


class TestDetectionLogSpeciesColumn(unittest.TestCase):
    def test_species_is_a_logged_column(self):
        self.assertIn("species", DetectionLog.FIELDS)
        self.assertEqual(DetectionLog.FIELDS[-1], "species")


if __name__ == "__main__":
    unittest.main()
