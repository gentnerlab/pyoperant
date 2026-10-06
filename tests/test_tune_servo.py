# -*- coding: utf-8 -*-
"""
Tests scripts/tune_servo.py's config-writing logic in isolation, without
needing real servo/pigpio hardware -- that's the part with real risk
(reading/writing a live box's panel_config.json) and the part this
session's redesign changed twice: first from regex-editing
local_pi_revd.py directly (which permanently blocked that box from ever
git-pulling pyoperant again -- see project memory), then from a per-
subject config.json (which would silently lose a box's calibration the
next time a different bird was assigned to it) to this box-level file.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "tune_servo.py")

# raspi_gpio_ imports pigpio unconditionally (real Rev D hardware) -- not
# installed on a dev machine.
if "pigpio" not in sys.modules:
    try:
        import pigpio  # noqa: F401
    except ImportError:
        sys.modules["pigpio"] = MagicMock()

spec = importlib.util.spec_from_file_location("tune_servo", SCRIPT_PATH)
tune_servo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tune_servo)


class TestWriteAnglesToConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_path = os.path.join(self.tmp.name, "panel_config.json")
        self.path_patch = patch.object(tune_servo, "PANEL_CONFIG_PATH", self.config_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def _read_config(self):
        with open(self.config_path) as f:
            return json.load(f)

    def test_creates_the_file_when_it_does_not_exist_yet(self):
        self.assertFalse(os.path.isfile(self.config_path))
        with patch("builtins.input", return_value="y"):
            tune_servo._write_angles_to_config(47.0, 17.0)
        config = self._read_config()
        self.assertEqual(config["hopper_up_angle"], 47.0)
        self.assertEqual(config["hopper_down_angle"], 17.0)
        # nothing to back up when the file didn't exist before
        self.assertFalse(os.path.isfile(self.config_path + ".bak_before_hopper_tuning"))

    def test_updates_an_existing_file_and_preserves_other_keys(self):
        with open(self.config_path, "w") as f:
            json.dump({"some_other_future_key": "keep me"}, f)
        with patch("builtins.input", return_value="y"):
            tune_servo._write_angles_to_config(47.0, 17.0)
        config = self._read_config()
        self.assertEqual(config["hopper_up_angle"], 47.0)
        self.assertEqual(config["hopper_down_angle"], 17.0)
        self.assertEqual(config["some_other_future_key"], "keep me")

    def test_backup_created_only_when_a_prior_file_existed(self):
        with open(self.config_path, "w") as f:
            json.dump({"hopper_up_angle": 40.0, "hopper_down_angle": 5.0}, f)
        backup_path = self.config_path + ".bak_before_hopper_tuning"
        with patch("builtins.input", return_value="y"):
            tune_servo._write_angles_to_config(47.0, 17.0)
        self.assertTrue(os.path.isfile(backup_path))
        with open(backup_path) as f:
            backup = json.load(f)
        self.assertEqual(backup["hopper_up_angle"], 40.0)  # pre-write content, not new

    def test_declining_the_prompt_writes_nothing(self):
        with patch("builtins.input", return_value="n"):
            tune_servo._write_angles_to_config(47.0, 17.0)
        self.assertFalse(os.path.isfile(self.config_path))

    def test_already_matching_values_are_a_no_op(self):
        with open(self.config_path, "w") as f:
            json.dump({"hopper_up_angle": 47.0, "hopper_down_angle": 17.0}, f)
        with patch("builtins.input") as mock_input:
            tune_servo._write_angles_to_config(47.0, 17.0)
            mock_input.assert_not_called()  # never even asks -- nothing to change

    def test_unparseable_existing_file_is_reported_not_crashed(self):
        with open(self.config_path, "w") as f:
            f.write("{not valid json")
        with patch("builtins.input") as mock_input:
            tune_servo._write_angles_to_config(47.0, 17.0)
            mock_input.assert_not_called()  # bails out before ever prompting
        # the broken file is left alone, not clobbered
        with open(self.config_path) as f:
            self.assertEqual(f.read(), "{not valid json")


class TestReleaseServo(unittest.TestCase):
    """The 'r' command's whole job is to put the PCA9685 channel in
    FULL_OFF so the servo stops getting pulses -- test that against the
    real PWM class's actual register write, not just that a method got
    called, since a wrong register value would silently do nothing (or
    worse, drive the servo somewhere)."""

    def test_delegates_a_negative_duty_cycle_for_the_given_channel(self):
        raspi = MagicMock()
        tune_servo.release_servo(raspi, 3)
        raspi.pwm_servo.set_duty_cycle.assert_called_once_with(3, -1)

    def test_writes_the_pca9685_full_off_bit_for_that_channel_only(self):
        from pyoperant.interfaces.raspi_gpio_ import PWM

        pi = MagicMock()
        pwm = PWM(pi, address=0x45)
        pi.reset_mock()

        raspi = MagicMock()
        raspi.pwm_servo = pwm
        tune_servo.release_servo(raspi, 0)

        # LED0_ON_L is 0x06, 4 registers per channel: ON_L, ON_H, OFF_L,
        # OFF_H. FULL_OFF is bit 4 of OFF_H (0x10); ON stays 0.
        pi.i2c_write_i2c_block_data.assert_called_once_with(
            pwm.h, 0x06 + 4 * 0, [0x00, 0x00, 0x00, 0x10])


if __name__ == "__main__":
    unittest.main()
