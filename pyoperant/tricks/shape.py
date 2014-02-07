import random
from pyoperant import utils

class Shaper(object):

	def __init__(self, panel, hopper_trials=100, error_callback=None):
		self.panel = panel
		self.error_callback = error_callback
		self.hopper_block_count = 0;

	def run_shape(self):
		utils.run_state_machine(	start_in='hopper_block',
									error_state='hopper_block',
									error_callback=self.error_callback,
									hopper_block=self._hopper_block(),
									peck_block=self._peck_block(),
									response_block=self._response_block())

"""
Block 1:  Hopper comes up on VI (stays up for 5 s) for the first day 
that the animal is in the apparatus. Center key flashes for 5 sec, prior 
to the hopper access. If the center key is pressed while flashing, then 
the hopper comes up and then the session jumps to block 2 immediately
"""
	def _hopper_block(self):
		utils.run_state_machine(	start_in='wait',
									error_callback=self.error_callback
									wait=self.wait_block(10,40,'flash_mid'),
									flash_mid=self.flash(panel.mid, 5, 'reward'),
									reward=self.reward(5, 'wait'))

	def _peck_block(self):
		pass

	def _response_block(self):
		pass

	def _wait_block(self, t_min, t_max, next_state):
		if t_min == t_max:
			t = t_max
		else:
			t = random.randrange(t_min, t_max)
		utils.wait(t)
		return next_state

	def flash(self, component, duration, next_state):
		component.flash(dur=duration)
		return next_state

"""
TODO: catch errors here
"""
	def reward(self, value, next_state):
		self.panel.reward(value=value)
		return next_state