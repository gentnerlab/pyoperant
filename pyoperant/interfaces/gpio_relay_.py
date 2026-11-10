import logging

import pigpio

from pyoperant.interfaces import base_
from pyoperant import InterfaceError

logger = logging.getLogger(__name__)


class GpioRelayInterface(base_.BaseInterface):
    """Drives plain on/off outputs (e.g. a relay's control input) from Pi
    GPIO pins through pigpiod -- no PCA9685 chips, unlike
    raspi_gpio_.RaspberryPiInterface.

    inverted -- if True, a logical True is driven as a low pin level.
        Wire a "normally on" relay output (e.g. the Digital Loggers IoT
        Relay's) with inverted=True: the control signal is then only
        asserted while the logical output is False (light off), so a Pi
        crash, power loss or pigpiod exit leaves the light ON.

    close() releases the pin to a pulled-down input rather than leaving
    it driven, so a clean shutdown also falls back to the relay's
    unpowered state.
    """

    def __init__(self, device_name='pi', inverted=False, *args, **kwargs):
        super(GpioRelayInterface, self).__init__(*args, **kwargs)
        self.device_name = device_name
        self.inverted = inverted
        self._channels = set()
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise InterfaceError(
                "Could not connect to pigpiod -- is it running? "
                "(sudo systemctl enable --now pigpiod)")

    def __str__(self):
        return "GPIO relay outputs on %s" % self.device_name

    def open(self):
        pass

    def close(self):
        for channel in self._channels:
            self.pi.set_mode(channel, pigpio.INPUT)
            self.pi.set_pull_up_down(channel, pigpio.PUD_DOWN)
        self.pi.stop()

    def _level(self, value):
        return 1 if bool(value) != self.inverted else 0

    def _config_write(self, channel, **kwargs):
        self._channels.add(channel)
        self.pi.set_mode(channel, pigpio.OUTPUT)

    def _read_bool(self, channel, **kwargs):
        return (self.pi.read(channel) == 1) != self.inverted

    def _write_bool(self, channel, value, **kwargs):
        self.pi.write(channel, self._level(value))
        return bool(value)
