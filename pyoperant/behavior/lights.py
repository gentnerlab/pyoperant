# -*- coding: utf-8 -*-
"""
This submodule controls the light schedule in the animal's environment.
It is documented in more detail in the main pyoperant module $pyoperant.components
"""

from pyoperant import utils, components
from pyoperant.behavior import base

class Lights(base.BaseExp):
    """A session-less behavior: just keeps the house light on `light_schedule`
    and, optionally, offers the bird free access to the hopper on
    `free_food_schedule`. Useful for holding a bird on a light/feeding
    schedule between real experiments, without running any trials.

    The two schedules are independent -- `free_food_schedule` doesn't have
    to match `light_schedule`, and free feeding is skipped entirely if
    `free_food_schedule` isn't set in the config (same as other behaviors).
    Both use the same format as `light_schedule`, e.g.
    [["07:00", "19:00"]], and are checked via `utils.check_time`.
    """
    def __init__(self,  *args, **kwargs):
        super(Lights, self).__init__(*args, **kwargs)
        self.req_panel_attr.append('reward')

    def panel_reset(self):
        try:
            self.panel.reset()
        except components.HopperWontDropError:
            pass

    def _run_idle(self):
        """Same as BaseExp._run_idle, except the free-food check doesn't
        require check_session_schedule() -- Lights has no session concept
        of its own, so that gate would otherwise make free_food_schedule
        silently inert here."""
        self.log.debug('Starting _run_idle')
        if self.check_light_schedule() == False:
            return 'sleep'
        elif self._check_free_food_block():
            return 'free_food_block'
        else:
            self.panel_reset()
            self.log.debug('idling...')
            utils.wait(self.parameters['idle_poll_interval'])
            return 'idle'

    def _free_food(self):
        """A solenoid shouldn't be held energized continuously, so
        BaseExp._free_food cycles it up/down for the duration of the
        schedule -- that's still correct here for a solenoid hopper. A
        servo can safely hold the raised position, though, so use a
        continuous raise/hold/lower instead of cycling it.

        Falls back to the solenoid-style cycling behavior if the panel's
        hopper actuator can't be determined."""
        if getattr(getattr(self.panel, 'hopper', None), '_actuator', None) == 'servo':
            return self._free_food_continuous()
        return super(Lights, self)._free_food()

    def _free_food_continuous(self):
        """Servo-hopper free food: raise once, hold for as long as
        free_food_schedule stays active, then lower once."""
        self.log.debug('Starting continuous free food (servo hopper)')
        try:
            self.panel.hopper.up()
        except components.HopperWontComeUpError:
            self.log.warning("Hopper did not come up for free food")
            return 'idle'

        while self._check_free_food_block():
            utils.wait(self.parameters['idle_poll_interval'])

        try:
            self.panel.hopper.down()
        except components.HopperWontDropError:
            self.log.warning("Hopper did not go down after free food")

        return 'idle'
