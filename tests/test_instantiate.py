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

PlacePrefExp24hr isn't covered here yet -- open_all_perches() used to call
utils.Visit(), which doesn't exist anywhere in pyoperant.utils, so the
class could never get past its first beam-break; that's now fixed (it
uses the class's own local Visit() instead), but Tier 2 coverage hasn't
been built. PlacePrefExp (the non-24hr version) has been removed --
confirmed superseded by PlacePrefExp24hr, not something to migrate.
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

# lights.py's song_recording path lazily imports pyoperant.song_recording,
# whose capture-layer modules import pyaudio for format constants (see
# pyoperant.song_recording._pcm) -- not installed on a dev machine either.
if "pyaudio" not in sys.modules:
    try:
        import pyaudio  # noqa: F401
    except ImportError:
        sys.modules["pyaudio"] = MagicMock()

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
from pyoperant import utils  # noqa: E402


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

    def test_panel_hw_id_preferred_name_is_mirrored_to_legacy_key(self):
        """New-style config using panel_hw_id must also populate the old
        panel_name key -- protects any code (including glab_behaviors, a
        private repo not auditable from here) still reading the old name
        directly, per base.py's BaseExp.__init__."""
        config = _load_config("Lights")
        config.pop("panel_name", None)
        config["panel_hw_id"] = "1"
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            exp = Lights(panel=FakePanel(), **config)
        self.assertEqual(exp.parameters["panel_hw_id"], "1")
        self.assertEqual(exp.parameters["panel_name"], "1")

    def test_legacy_panel_name_still_works_and_is_mirrored_forward(self):
        """An existing, already-deployed config.json using the old
        panel_name key must keep working unchanged, AND populate the new
        panel_hw_id key too, so newly-updated code reading the preferred
        name still finds a value from an old config. Sets panel_name
        explicitly rather than relying on example_configs/Lights.json
        still using it -- that file is migrated to panel_hw_id (see the
        "preferred" test above), so this needs its own legacy-shaped
        config to actually exercise the old path."""
        config = _load_config("Lights")
        config.pop("panel_hw_id", None)
        config["panel_name"] = "1"
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            exp = Lights(panel=FakePanel(), **config)
        self.assertEqual(exp.parameters["panel_name"], "1")
        self.assertEqual(exp.parameters["panel_hw_id"], "1")

    def test_panel_hw_id_takes_precedence_when_both_given(self):
        """Not a configuration anyone should actually write, but the
        precedence needs to be defined and correct if it happens (e.g. a
        half-migrated config)."""
        config = _load_config("Lights")
        config["panel_name"] = "1"
        config["panel_hw_id"] = "2"
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            exp = Lights(panel=FakePanel(), **config)
        self.assertEqual(exp.parameters["panel_hw_id"], "2")
        self.assertEqual(exp.parameters["panel_name"], "2")

    def test_Lights_free_food_during_idle(self):
        """free_food_schedule should trigger the free-food state directly
        from _run_idle, without needing check_session_schedule() -- see
        lights.py's _run_idle override.

        Note: doesn't drive exp._free_food() itself -- with an always-on
        schedule its inner wait/food/checker loop (base.py) never exits,
        by design (it's meant to keep cycling for as long as the schedule
        window is open). deliver_free_food() is the actual reward-delivery
        primitive that loop calls each pass, so exercise that directly."""
        config = _load_config("Lights")
        config["free_food_schedule"] = [["00:00", "23:59"]]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            exp = Lights(panel=panel, **config)
            self.assertEqual(exp._run_idle(), 'free_food_block')

            exp.deliver_free_food(10, 'checker')()
            self.assertEqual(panel.reward_calls, [10])

    def test_Lights_free_food_servo_continuous(self):
        """Servo hopper: _free_food should raise once, hold while the
        schedule stays open, then lower once -- not cycle like the
        solenoid path does."""
        config = _load_config("Lights")
        config["free_food_schedule"] = [["00:00", "23:59"]]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel(hopper_actuator="servo")
            exp = Lights(panel=panel, **config)

            with patch("pyoperant.utils.wait"), \
                 patch.object(exp, "_check_free_food_block", side_effect=[True, False]):
                self.assertEqual(exp._free_food(), 'idle')

            self.assertEqual(panel.hopper.calls, ["up", "down"])

    def test_Lights_free_food_solenoid_cycles(self):
        """Solenoid hopper: _free_food should fall through to BaseExp's
        existing cycling behavior (feed via panel.reward each pass)
        unchanged -- the hopper is never held continuously up."""
        config = _load_config("Lights")
        config["free_food_schedule"] = [["00:00", "23:59"]]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel(hopper_actuator="solenoid")
            exp = Lights(panel=panel, **config)

            with patch("pyoperant.utils.wait"), \
                 patch("pyoperant.utils.check_time", return_value=False):
                self.assertEqual(exp._free_food(), 'idle')

            self.assertEqual(panel.reward_calls, [10])
            self.assertEqual(panel.hopper.calls, [])

    def test_Lights_recording_enabled_routes_to_session(self):
        """song_recording.enabled=True should route _run_idle into the
        normal BaseExp session state (session_pre/main/post), where the
        monitor thread lives -- see lights.py's _run_idle override. This
        is the fix for the bug where _run_idle could never reach 'session'
        for Lights at all (neither the free-food override nor, before it,
        BaseExp's own check_session_schedule()-gated branch, since Lights
        never overrides check_session_schedule). Lights.json's own default
        free_food_schedule is always-on (see e50aff6), so it's cleared here
        -- otherwise free food would take priority and mask this branch;
        that interaction is covered separately below."""
        config = _load_config("Lights")
        config.pop("free_food_schedule", None)
        config["song_recording"] = {"enabled": True}
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            exp = Lights(panel=panel, **config)
            self.assertEqual(exp._run_idle(), 'session')

    def test_Lights_recording_disabled_stays_idle(self):
        """Without song_recording in config, _run_idle must behave exactly
        as before -- zero regression for existing non-recording Lights
        boxes. Lights.json's own default free_food_schedule is always-on
        (see e50aff6), so it's cleared here to isolate the branch under
        test; that interaction is covered separately below."""
        config = _load_config("Lights")
        config.pop("free_food_schedule", None)
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            exp = Lights(panel=panel, **config)
            with patch("pyoperant.utils.wait"):
                self.assertEqual(exp._run_idle(), 'idle')

    def test_Lights_free_food_takes_priority_over_recording(self):
        """When both free_food_schedule and song_recording are active at
        once, free food wins -- same precedence _run_idle documents."""
        config = _load_config("Lights")
        config["free_food_schedule"] = [["00:00", "23:59"]]
        config["song_recording"] = {"enabled": True}
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            exp = Lights(panel=panel, **config)
            self.assertEqual(exp._run_idle(), 'free_food_block')

    def test_Lights_session_pre_skips_gracefully_without_microphone(self):
        """FakePanel has no .microphone -- session_pre() (building the
        detection pipeline and starting the monitor thread) must degrade
        gracefully, not crash: Lights has to keep controlling the light
        schedule regardless of whether a panel even has a mic configured
        (e.g. a Rev C board, or any panel where song_recording just isn't
        wired up yet)."""
        config = _load_config("Lights")
        config["song_recording"] = {"enabled": True}
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            self.assertFalse(hasattr(panel, "microphone"))
            exp = Lights(panel=panel, **config)
            try:
                self.assertEqual(exp.session_pre(), 'main')
            except Exception as e:
                self.fail("session_pre() should degrade gracefully without "
                          "a microphone, not raise: {}: {}".format(
                              type(e).__name__, e))
            self.assertIsNone(exp._monitor_thread)

            try:
                self.assertIsNone(exp.session_post())
            except Exception as e:
                self.fail("session_post() should be a no-op when the "
                          "monitor thread never started: {}: {}".format(
                              type(e).__name__, e))

    def test_emergency_shutdown_noop_without_monitor(self):
        """emergency_shutdown() (called from scripts/behave's SIGTERM/
        SIGINT handler -- see its module docstring) must be a safe no-op
        when the monitor was never started, same as session_post() above --
        it can fire from ANY state, including before session_pre() ever
        ran."""
        config = _load_config("Lights")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            exp = Lights(panel=panel, **config)
            try:
                exp.emergency_shutdown()
            except Exception as e:
                self.fail("emergency_shutdown() should be a no-op when the "
                          "monitor thread never started: {}: {}".format(
                              type(e).__name__, e))

    def test_emergency_shutdown_stops_running_monitor(self):
        """The actual fix: emergency_shutdown() must stop a LIVE monitor
        thread, not just no-op -- this is what a bare sys.exit() from the
        old clean() handler skipped entirely (daemon thread, no chance to
        run its own cleanup), which is what let a killed process leave the
        USB-audio device wedged (see project_vocal_recorder memory,
        2026-09-10). Delegates to _stop_monitor(), already exercised by
        session_post() elsewhere -- just confirm emergency_shutdown()
        actually calls it."""
        config = _load_config("Lights")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = prepare_experiment_dirs(config, tmp_dir)
            panel = FakePanel()
            exp = Lights(panel=panel, **config)
            with patch.object(exp, "_stop_monitor") as mock_stop:
                exp.emergency_shutdown()
            mock_stop.assert_called_once()


class TestResolvePanelHwId(unittest.TestCase):
    """utils.resolve_panel_hw_id() picks which PANELS[...] key a run
    controls -- see its docstring for the panel/host naming history this
    is untangling. PANELS is always a single-entry {"1": ...} dict on a
    real board; a two-entry fake here is enough to exercise every branch
    without needing real hardware classes."""

    PANELS = {"1": object(), "2": object()}

    def test_cli_value_wins_even_if_config_disagrees(self):
        resolved = utils.resolve_panel_hw_id("2", "1", self.PANELS)
        self.assertEqual(resolved, "2")

    def test_cli_value_missing_falls_back_to_config(self):
        resolved = utils.resolve_panel_hw_id(None, "2", self.PANELS)
        self.assertEqual(resolved, "2")

    def test_both_missing_falls_back_to_default(self):
        resolved = utils.resolve_panel_hw_id(None, None, self.PANELS)
        self.assertEqual(resolved, utils.DEFAULT_PANEL_HW_ID)

    def test_invalid_config_value_falls_back_to_default_not_crash(self):
        """The real bug this is fixing: some fleet config.json files have
        the box's own hostname (e.g. "Magpi11") sitting in panel_hw_id
        instead of "1" -- a stale value like that must not crash an
        unattended, cron-driven box."""
        resolved = utils.resolve_panel_hw_id(None, "Magpi11", self.PANELS)
        self.assertEqual(resolved, utils.DEFAULT_PANEL_HW_ID)

    def test_invalid_config_value_logs_a_warning(self):
        logger = MagicMock()
        utils.resolve_panel_hw_id(None, "Magpi11", self.PANELS, logger=logger)
        logger.warning.assert_called_once()

    def test_invalid_cli_value_raises_clearly(self):
        """Unlike a bad config value, an explicit CLI override is a
        direct user request -- a typo there should raise immediately and
        legibly, not be silently replaced."""
        with self.assertRaises(KeyError):
            utils.resolve_panel_hw_id("nonexistent", None, self.PANELS)

    def test_default_itself_must_be_a_valid_panel(self):
        with self.assertRaises(KeyError):
            utils.resolve_panel_hw_id(None, None, self.PANELS, default="nonexistent")


class TestCheckCmdlineParamsPanelSafety(unittest.TestCase):
    """check_cmdline_params()'s box-number check used to call
    digits_only(panel_hw_id) unconditionally, which raises a bare
    TypeError/ValueError if panel_hw_id is missing or non-numeric (e.g. a
    fleet config.json with a hostname in that field). This is a safety
    check only -- no change to what counts as a match, just no crash."""

    def test_missing_panel_hw_id_fails_clearly_not_crash(self):
        result = utils.check_cmdline_params(
            {"subject": "B1"}, {"box": 1, "subj": "B1"}
        )
        self.assertFalse(result)

    def test_non_numeric_panel_hw_id_fails_clearly_not_crash(self):
        result = utils.check_cmdline_params(
            {"subject": "B1", "panel_hw_id": "Magpi11"}, {"box": 1, "subj": "B1"}
        )
        self.assertFalse(result)

    def test_matching_numeric_panel_hw_id_still_passes(self):
        result = utils.check_cmdline_params(
            {"subject": "B1", "panel_hw_id": "1"}, {"box": 1, "subj": "B1"}
        )
        self.assertTrue(result)

    def test_box_not_in_cmd_line_skips_check_as_before(self):
        result = utils.check_cmdline_params(
            {"subject": "B1"}, {"subj": "B1"}
        )
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
