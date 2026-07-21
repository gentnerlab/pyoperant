# -*- coding: utf-8 -*-
"""
Tier 2: instantiate each pyoperant/behavior/*.py Behavior class from its
real example_configs/*.json and step it through some real usage, with
hardware replaced by tests/fixtures.py's FakePanel. Catches logic-level
bugs Tier 0 (syntax) and Tier 1 (import) can't -- e.g. file modes,
signature mismatches between call sites -- by actually exercising __init__
and the trial state machine, not just loading the module.

Mirrors py-behaviors' tests/test_instantiate.py. TwoAltChoiceExp and
ThreeACMatchingExp share that file's approach (bypass session_main()'s
full scheduling loop, call new_trial()/run_trial() directly). Lights
doesn't fit that pattern (no trial concept of its own beyond BaseExp's
defaults), so it gets its own, simpler test.

PlacePrefExp/PlacePrefExp24hr are deliberately not covered here yet --
open_all_perches() calls utils.Visit(), which doesn't exist anywhere in
pyoperant.utils, so neither class can get past its first beam-break. Under
investigation; add their Tier 2 coverage once that's resolved.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIGS_DIR = os.path.join(REPO_ROOT, "example_configs")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# place_pref.py/place_pref_24hr.py import serial unconditionally at module
# level (real Arduino connection for speaker switching) -- not installed on
# a dev machine. Stub it before importing pyoperant.behavior, which eagerly
# imports both via __init__.py.
if "serial" not in sys.modules:
    try:
        import serial  # noqa: F401
    except ImportError:
        sys.modules["serial"] = MagicMock()

from fixtures import (  # noqa: E402
    FakePanel,
    prepare_experiment_dirs,
    make_dummy_wavs_for_stims,
    make_dummy_wavs_for_config_stims,
)

from pyoperant.behavior import (  # noqa: E402
    TwoAltChoiceExp,
    Lights,
    ThreeACMatchingExp,
)


def _load_config(name):
    with open(os.path.join(CONFIGS_DIR, name + ".json")) as f:
        config = json.load(f)
    config.pop("comments", None)
    if "email" in config.get("log_handlers", []):
        config["log_handlers"] = [h for h in config["log_handlers"] if h != "email"]
    return config


class TestTwoAltChoiceFamily(unittest.TestCase):
    """TwoAltChoiceExp and ThreeACMatchingExp both drive real trials via
    new_trial()/run_trial(), same primitives session_main() itself uses,
    just without the outer scheduling loop (which depends on real
    light-schedule/time-of-day checks via ephem)."""

    def _run(self, cls, config_name):
        config = _load_config(config_name)
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            make_dummy_wavs_for_config_stims(config)
            panel = FakePanel()

            with patch("pyoperant.utils.wait"):
                exp = cls(panel=panel, **config)
                make_dummy_wavs_for_stims(exp.parameters)
                exp.check_session_schedule = lambda: True
                exp.init_summary()
                exp.session_pre()
                exp.trials = []
                exp.do_correction = False
                exp.session_id += 1

                conditions = (
                    exp.parameters.get("block_design", {})
                    .get("blocks", {})
                    .get("default", {})
                    .get("conditions", [])
                )
                if not conditions:
                    conditions = [{"class": k} for k in list(exp.parameters["classes"])[:2]]
                for cond in conditions[:2]:
                    exp.new_trial(cond)
                    exp.run_trial()
            return exp

    def test_TwoAltChoiceExp(self):
        try:
            self._run(TwoAltChoiceExp, "TwoAltChoiceExp")
        except Exception as e:
            self.fail("TwoAltChoiceExp fails to instantiate/run: {}: {}".format(
                type(e).__name__, e))

    def test_ThreeACMatchingExp(self):
        try:
            self._run(ThreeACMatchingExp, "ThreeACMatchingExp")
        except Exception as e:
            self.fail("ThreeACMatchingExp fails to instantiate/run: {}: {}".format(
                type(e).__name__, e))


class TestLights(unittest.TestCase):
    """Lights has no trial/session concept of its own beyond BaseExp's
    defaults -- just confirm it constructs and panel_reset() works."""

    def test_Lights(self):
        config = _load_config("Lights")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            try:
                exp = Lights(panel=panel, **config)
                exp.panel_reset()
            except Exception as e:
                self.fail("Lights fails to instantiate/run: {}: {}".format(
                    type(e).__name__, e))
            self.assertEqual(panel.reset_calls, 1)


if __name__ == "__main__":
    unittest.main()
