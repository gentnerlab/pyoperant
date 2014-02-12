import random
import datetime as dt
from pyoperant import utils

class Shaper(object):

    def __init__(self, panel, log, parameters, error_callback=None):
        self.panel = panel
        self.log = log
        self.parameters = parameters
        self.error_callback = error_callback
        self.recent_state = 'hopper_block'

    def run_shape(self, start_state='hopper_block'):
        utils.run_state_machine(    start_in=start_state,
                                    error_state='hopper_block',
                                    error_callback=self.error_callback,
                                    hopper_block=self._hopper_block('peck_block'),
                                    peck_block=self._peck_block('response_block','hopper_block'),
                                    response_block=self._response_block(None, 'peck_block'),
                                    sleep_block=self._run_sleep)

# Block 1:  Hopper comes up on VI (stays up for 5 s) for the first day
# that the animal is in the apparatus. Center key flashes for 5 sec, prior
# to the hopper access. If the center key is pressed while flashing, then
# the hopper comes up and then the session jumps to block 2 immediately

    def _hopper_block(self, next_state):
        def temp():
            self.recent_state = 'hopper_block'
            utils.run_state_machine(    start_in='init',
                                        error_state='wait',
                                        error_callback=self.error_callback,
                                        init=self._block_init('wait'),
                                        wait=self._wait_block(10, 40,'check'),
                                        check=self._check_block('flash_mid', 1, float('inf')),
                                        flash_mid=self._flash_poll(self.panel.center, 5, 'reward', 'pre_reward'),
                                        pre_reward=self._pre_reward('reward'),
                                        reward=self.reward(5, 'check2'),
                                        check2=self._check_block('wait', 1, float('inf')))
            if not utils.check_time(self.parameters['light_schedule']):
                return 'sleep_block'
            return next_state
        return temp

# Block 2:  The center key flashes until pecked.  When pecked the hopper comes up for
#           4 sec. Run 100 trials.
#           reverts to revert_state if no response before timeout (60*60*3=10800)
    def _peck_block(self, next_state, revert_state, reps=100, revert_timeout=10800):
        def temp():
            self.recent_state = 'peck_block'
            utils.run_state_machine(    start_in='init',
                                        error_state='check',
                                        error_callback=self.error_callback,
                                        init=self._block_init('check'),
                                        check=self._check_block('poll_mid', reps, revert_timeout),
                                        poll_mid=self._flash_poll(self.panel.center, 10, 'check', 'pre_reward'),
                                        pre_reward=self._pre_reward('reward'),
                                        reward=self.reward(4, 'check'))
            if not utils.check_time(self.parameters['light_schedule']):
                return 'sleep_block'
            if self.responded_block:
                return next_state
            else:
                return revert_state
        return temp

# Block 3:  The center key flashes until pecked, then either the right or left (p = .5)
#           key flashes until pecked, then the hopper comes up for 3 sec. Run 100 trials.

    def _response_block(self, next_state, revert_state, reps=100, revert_timeout=10800):
        def temp():
            self.recent_state = 'response_block'
            utils.run_state_machine(    start_in='init',
                                        error_state='check',
                                        error_callback=self.error_callback,
                                        init=self._block_init('check'),
                                        check=self._check_block('poll_mid', reps, revert_timeout),
                                        poll_mid=self._flash_poll(self.panel.center, 10, 'check', 'coin_flip'),
                                        coin_flip=self._coin_flip('check_right', 'check_left', p=.5),
                                        check_right=self._check_block('poll_right', reps, revert_timeout),
                                        poll_right=self._flash_poll(self.panel.right, 10, 'check_right', 'pre_reward'),
                                        check_left=self._check_block('poll_left', reps, revert_timeout),
                                        poll_left=self.flash_poll(self.panel.left, 10, 'check_left', 'pre_reward'),
                                        pre_reward=self._pre_reward('reward'),
                                        reward=self.reward(3))
            if not utils.check_time(self.parameters['light_schedule']):
                return 'sleep_block'
            if self.responded_block:
                return next_state
            else:
                return revert_state
        return temp

# Block 4:  Wait for peck to non-flashing center key, then right or left key flashes
#           until pecked, then food for 2.5 sec.   Run 100 trials.

    def _block_init(self, next_state):
        def temp():
            self.block_start = dt.datetime.now()
            self.responded_block = False
            self.response_counter = 0
            return next_state
        return temp

    def _check_block(self, next_state, reps, revert_timeout):
        def temp():
            if not self.responded_block:
                elapsed_time = (dt.datetime.now() - self.block_start).total_seconds()
                if elapsed_time > revert_timeout:
                    return None
            else:
                if self.response_counter >= reps:
                    return None
            if not utils.check_time(self.parameters['light_schedule']):
                return None
            return next_state
        return temp

    def _pre_reward(self, next_state):
        def temp():
            self.responded_block = True
            self.response_counter = self.response_counter + 1
            return next_state
        return temp

    def _wait_block(self, t_min, t_max, next_state):
        def temp():
            if t_min == t_max:
                t = t_max
            else:
                t = random.randrange(t_min, t_max)
            utils.wait(t)
            return next_state
        return temp

    def _flash_poll(self, component, duration, next_state, reward_state=None):
        def temp():
            utils.run_state_machine(    start_in='init',
                                        init=self._polling_init('main'),
                                        main=self._flashing_main(component, duration, 1))
            if self.responded_poll:
                return reward_state
            else:
                return next_state
        return temp

    def _polling_init(self, next_state):
        def temp():
            self.polling_start = dt.datetime.now()
            self.responded_poll = False
            return next_state
        return temp

    def _flashing_main(self, component, duration, period):
        def temp():
            elapsed_time = (dt.datetime.now() - self.polling_start).total_seconds()
            if elapsed_time <= duration:
                if ((elapsed_time % period) - (period / 2.0)) < 0:
                    component.on()
                else:
                    component.off()
                if component.status():
                    component.off()
                    self.responded_poll = True
                    return None
                return 'main'
            else:
                component.off()
                return None
        return temp

    def _light_poll(self, component, duration, next_state, reward_state=None):
        def temp():
            utils.run_state_machine(    start_in='init',
                                        init=self._polling_init('main'),
                                        main=self._light_main(component, duration))
            if self.responded_poll:
                return reward_state
            else:
                return next_state
        return temp

    def _light_main(self, component, duration):
        def temp():
            elapsed_time = (dt.datetime.now() - self.polling_start).total_seconds()
            if elapsed_time <= duration:
                component.on()
                if component.status():
                    component.off()
                    self.responded_poll = True
                    return None
                return 'main'
            else:
                component.off()
                return None
        return temp

#TODO: catch errors here
    def reward(self, value, next_state):
        def temp():
            self.panel.reward(value=value)
            return next_state
        return temp

    # defining functions for sleep
    #TODO: there should really be a separate sleeper or some better solution
    def sleep_pre(self):
        self.log.debug('lights off. going to sleep...')
        return 'main'

    def sleep_main(self):
        """ reset expal parameters for the next day """
        self.log.debug('sleeping...')
        self.panel.house_light.off()
        utils.wait(self.parameters['idle_poll_interval'])
        if not self.check_light_schedule():
            return 'main'
        else:
            return 'post'

    def sleep_post(self):
        self.log.debug('ending sleep')
        self.panel.house_light.on()
#        self.init_summary()
        return None

    def _run_sleep(self):
        utils.run_state_machine(start_in='pre',
                                error_state='post',
                                error_callback=self.log_error_callback,
                                pre=self.sleep_pre,
                                main=self.sleep_main,
                                post=self.sleep_post)
        return self.recent_state
