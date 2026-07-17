# -*- coding: utf-8 -*-
"""
Unit tests for Hopper and PeckPort components.

These tests use a FakeInterface to avoid any hardware dependency so they
can be run on a development machine without a Raspberry Pi.
"""

import datetime
import sys
import os
import unittest
from unittest.mock import patch, Mock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyoperant import hwio
from pyoperant.components import (
    Hopper, PeckPort,
    HopperWontComeUpError, HopperWontDropError, HopperAlreadyUpError,
)


class FakeInterface(object):
    """Minimal hardware interface stub — no real GPIO, I2C, or pigpio needed."""

    def __init__(self):
        self.values = {}

    def _callback(self, func=None, channel=None, **kwargs):
        pass

    def _config_read(self, channel, **kwargs):
        pass

    def _config_write(self, channel, **kwargs):
        pass

    def _read_bool(self, channel, **kwargs):
        return self.values.get(channel, False)

    def _write_bool(self, value, channel, **kwargs):
        self.values[channel] = value
        return value

    def _write_pwm(self, value, channel, servo=False, **kwargs):
        self.values[channel] = value
        return value

    def _poll(self, channel, timeout=None, **kwargs):
        return datetime.datetime.now()


def make_bool_input(iface, channel):
    return hwio.BooleanInput(interface=iface, params={'channel': channel})

def make_bool_output(iface, channel):
    return hwio.BooleanOutput(interface=iface, params={'channel': channel})

def make_pwm_output(iface, channel):
    return hwio.PWMOutput(interface=iface, params={'channel': channel})


# ---------------------------------------------------------------------------
# Hopper: max_lag defaults
# ---------------------------------------------------------------------------

class TestHopperMaxLag(unittest.TestCase):

    def setUp(self):
        self.iface = FakeInterface()
        self.ir = make_bool_input(self.iface, 5)

    def test_servo_default_max_lag(self):
        servo = make_pwm_output(self.iface, 0)
        hopper = Hopper(IR=self.ir, servo=servo, up_angle=45, down_angle=10)
        self.assertEqual(hopper.max_lag, 1.0)

    def test_solenoid_default_max_lag(self):
        solenoid = make_bool_output(self.iface, 1)
        hopper = Hopper(IR=self.ir, solenoid=solenoid)
        self.assertEqual(hopper.max_lag, 0.3)

    def test_explicit_max_lag_overrides_servo_default(self):
        servo = make_pwm_output(self.iface, 0)
        hopper = Hopper(IR=self.ir, servo=servo, up_angle=45, down_angle=10, max_lag=2.5)
        self.assertEqual(hopper.max_lag, 2.5)

    def test_explicit_max_lag_overrides_solenoid_default(self):
        solenoid = make_bool_output(self.iface, 1)
        hopper = Hopper(IR=self.ir, solenoid=solenoid, max_lag=0.5)
        self.assertEqual(hopper.max_lag, 0.5)


# ---------------------------------------------------------------------------
# Hopper: constructor validation
# ---------------------------------------------------------------------------

class TestHopperValidation(unittest.TestCase):

    def setUp(self):
        self.iface = FakeInterface()
        self.ir = make_bool_input(self.iface, 5)

    def test_requires_solenoid_or_servo(self):
        with self.assertRaises(ValueError):
            Hopper(IR=self.ir)

    def test_rejects_both_solenoid_and_servo(self):
        solenoid = make_bool_output(self.iface, 1)
        servo = make_pwm_output(self.iface, 0)
        with self.assertRaises(ValueError):
            Hopper(IR=self.ir, solenoid=solenoid, servo=servo,
                   up_angle=45, down_angle=10)

    def test_servo_requires_up_and_down_angles(self):
        servo = make_pwm_output(self.iface, 0)
        with self.assertRaises(ValueError):
            Hopper(IR=self.ir, servo=servo)


# ---------------------------------------------------------------------------
# Hopper: check() IR polarity
# ---------------------------------------------------------------------------

class TestHopperCheck(unittest.TestCase):

    def _make_hopper(self, iface, inverted):
        ir = make_bool_input(iface, 5)
        solenoid = make_bool_output(iface, 1)
        return Hopper(IR=ir, solenoid=solenoid, inverted=inverted, max_lag=0.1)

    def test_not_inverted_high_is_broken(self):
        iface = FakeInterface()
        hopper = self._make_hopper(iface, inverted=False)
        iface.values[5] = True
        self.assertTrue(hopper.check())

    def test_not_inverted_low_is_clear(self):
        iface = FakeInterface()
        hopper = self._make_hopper(iface, inverted=False)
        iface.values[5] = False
        self.assertFalse(hopper.check())

    def test_inverted_low_is_broken(self):
        iface = FakeInterface()
        hopper = self._make_hopper(iface, inverted=True)
        iface.values[5] = False
        self.assertTrue(hopper.check())

    def test_inverted_high_is_clear(self):
        iface = FakeInterface()
        hopper = self._make_hopper(iface, inverted=True)
        iface.values[5] = True
        self.assertFalse(hopper.check())


# ---------------------------------------------------------------------------
# Hopper: up()
# ---------------------------------------------------------------------------

class TestHopperUp(unittest.TestCase):

    def setUp(self):
        self.iface = FakeInterface()
        self.ir = make_bool_input(self.iface, 5)
        servo = make_pwm_output(self.iface, 0)
        self.hopper = Hopper(IR=self.ir, servo=servo, up_angle=45, down_angle=10,
                             inverted=False, max_lag=0.5)

    def test_up_returns_datetime_when_beam_breaks(self):
        self.iface.values[5] = True  # beam immediately broken
        result = self.hopper.up()
        self.assertIsInstance(result, datetime.datetime)

    def test_up_raises_when_beam_never_breaks(self):
        self.iface.values[5] = False  # beam never breaks
        with self.assertRaises(HopperWontComeUpError):
            self.hopper.up()

    def test_up_moves_servo_to_down_on_failure(self):
        self.iface.values[5] = False
        try:
            self.hopper.up()
        except HopperWontComeUpError:
            pass
        self.assertEqual(self.iface.values[0], 10)  # back to down_angle


# ---------------------------------------------------------------------------
# Hopper: down()
# ---------------------------------------------------------------------------

class TestHopperDown(unittest.TestCase):

    def setUp(self):
        self.iface = FakeInterface()
        self.ir = make_bool_input(self.iface, 5)
        solenoid = make_bool_output(self.iface, 1)
        self.hopper = Hopper(IR=self.ir, solenoid=solenoid, inverted=False, max_lag=0.1)

    @patch('pyoperant.utils.wait')
    def test_down_succeeds_when_beam_clears(self, mock_wait):
        self.iface.values[5] = False  # beam clear after lowering
        result = self.hopper.down()
        self.assertIsInstance(result, datetime.datetime)

    @patch('pyoperant.utils.wait')
    def test_down_raises_when_beam_stays_broken(self, mock_wait):
        self.iface.values[5] = True  # beam still broken after lowering
        with self.assertRaises(HopperWontDropError):
            self.hopper.down()


# ---------------------------------------------------------------------------
# Hopper: feed()
# ---------------------------------------------------------------------------

class TestHopperFeed(unittest.TestCase):

    def setUp(self):
        self.iface = FakeInterface()
        self.ir = make_bool_input(self.iface, 5)
        solenoid = make_bool_output(self.iface, 1)
        self.hopper = Hopper(IR=self.ir, solenoid=solenoid, inverted=False, max_lag=0.1)

    def test_feed_raises_when_already_up(self):
        self.iface.values[5] = True  # beam already broken at start
        with self.assertRaises(HopperAlreadyUpError):
            self.hopper.feed(dur=0.5)

    @patch('pyoperant.utils.wait')
    def test_feed_complete_cycle(self, mock_wait):
        # Sequence: not up → beam breaks during up() → clears during down()
        check_returns = [False, True, False]
        check_iter = iter(check_returns)
        self.hopper.check = Mock(side_effect=lambda: next(check_iter))
        with patch.object(self.hopper, 'down', return_value=datetime.datetime.now()):
            result = self.hopper.feed(dur=0.5)
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# PeckPort: status() IR polarity
# ---------------------------------------------------------------------------

class TestPeckPortStatus(unittest.TestCase):

    def _make_port(self, iface, ir_channel, inverted):
        ir = make_bool_input(iface, ir_channel)
        led = make_pwm_output(iface, 4)
        return PeckPort(IR=ir, LED=led, name='l', inverted=inverted)

    def test_not_inverted_high_is_broken(self):
        # Rev D: beam broken = GPIO high
        iface = FakeInterface()
        port = self._make_port(iface, 6, inverted=False)
        iface.values[6] = True
        self.assertTrue(port.status())

    def test_not_inverted_low_is_clear(self):
        iface = FakeInterface()
        port = self._make_port(iface, 6, inverted=False)
        iface.values[6] = False
        self.assertFalse(port.status())

    def test_inverted_low_is_broken(self):
        iface = FakeInterface()
        port = self._make_port(iface, 6, inverted=True)
        iface.values[6] = False
        self.assertTrue(port.status())

    def test_inverted_high_is_clear(self):
        iface = FakeInterface()
        port = self._make_port(iface, 6, inverted=True)
        iface.values[6] = True
        self.assertFalse(port.status())


if __name__ == '__main__':
    unittest.main(verbosity=2)
