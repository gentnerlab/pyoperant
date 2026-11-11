import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod in ("pyaudio", "pigpio"):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()


class TestGpioRelayInterface(unittest.TestCase):
    def _iface(self, inverted):
        from pyoperant.interfaces import gpio_relay_
        with patch.object(gpio_relay_.pigpio, "pi") as pi_cls:
            iface = gpio_relay_.GpioRelayInterface(inverted=inverted)
        return iface, pi_cls.return_value

    def test_inverted_drives_pin_low_for_logical_true(self):
        iface, pi = self._iface(inverted=True)
        iface._write_bool(channel=17, value=True)
        pi.write.assert_called_with(17, 0)
        iface._write_bool(channel=17, value=False)
        pi.write.assert_called_with(17, 1)

    def test_non_inverted_is_direct(self):
        iface, pi = self._iface(inverted=False)
        iface._write_bool(channel=17, value=True)
        pi.write.assert_called_with(17, 1)

    def test_close_releases_pins_to_pulled_down_inputs(self):
        from pyoperant.interfaces import gpio_relay_
        iface, pi = self._iface(inverted=True)
        iface._config_write(channel=17)
        iface.close()
        pi.set_mode.assert_called_with(17, gpio_relay_.pigpio.INPUT)
        pi.set_pull_up_down.assert_called_with(17, gpio_relay_.pigpio.PUD_DOWN)

    def test_raises_when_pigpiod_unreachable(self):
        from pyoperant import InterfaceError
        from pyoperant.interfaces import gpio_relay_
        with patch.object(gpio_relay_.pigpio, "pi") as pi_cls:
            pi_cls.return_value.connected = False
            with self.assertRaises(InterfaceError):
                gpio_relay_.GpioRelayInterface()


class TestLitePanel(unittest.TestCase):
    def _panel(self, **kwargs):
        import pyoperant.local_pi_lite as rec
        with patch.object(rec.gpio_relay_, "GpioRelayInterface"), \
             patch.object(rec.pyaudio_, "PyAudioInterface"):
            return rec.Pi1(**kwargs)

    def test_has_light_and_microphone_only(self):
        panel = self._panel()
        self.assertTrue(hasattr(panel, "house_light"))
        self.assertTrue(hasattr(panel, "microphone"))
        self.assertFalse(hasattr(panel, "hopper"))

    def test_light_uses_relay_pin(self):
        panel = self._panel(relay_pin=22)
        self.assertEqual(panel.light_relay.params["channel"], 22)

    def test_reset_turns_light_on(self):
        panel = self._panel()
        panel.reset()
        panel.light_relay.interface._write_bool.assert_called_with(
            channel=17, value=True)


if __name__ == "__main__":
    unittest.main()
