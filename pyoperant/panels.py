import time

## Panel classes

class BasePanel(object):
    """Returns a panel instance.

    This class should be subclassed to define a local panel configuration.

    To build a panel, do the following in the __init__() method of your local 
        subclass:

    1. add instances of the necessary interfaces to the 'interfaces' dict 
        attribute:
        >>> self.interfaces['comedi'] = comedi.ComediInterface(device_name='/dev/comedi0')

    2. add inputs and outputs to the 'inputs' and 'outputs' list attributes:
        >>> for in_chan in range(4):
                self.inputs.append(hwio.BooleanInput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': 2,
                                                           'channel': in_chan
                                                           },
                                                 )
    3. add components constructed from your inputs and outputs:
        >>> self.hopper = components.Hopper(IR=self.inputs[3],solenoid=self.outputs[4])

    4. assign panel methods needed for operant behavior, such as 'reward':
        >>> self.reward = self.hopper.reward

    5. finally, define a reset() method that will set the entire panel to a 
        neutral state:

        >>> def reset(self):
        >>>     for output in self.outputs:
        >>>         output.set(False)
        >>>     self.house_light.write(True)
        >>>     return True

    """
    def __init__(self, *args,**kwargs):

        self.interfaces = {}

        self.inputs = []
        self.outputs = []

    def reset(self):
         raise NotImplementedError

    def test(self):
        self.reset()
        dur = 2.0
        auto = {}
        confirmed = {}

        def confirm(prompt):
            while True:
                resp = input('  %s (y/n): ' % prompt).strip().lower()
                if resp in ('y', 'n'):
                    return resp == 'y'
                print('  Please enter y or n.')

        # ------------------------------------------------------------------
        # Phase 1: autonomous run-through
        # ------------------------------------------------------------------
        print('\n=== Phase 1: Autonomous test ===')

        print('Testing house light...')
        try:
            self.house_light.on()
            print('  houselight should be ON')
            time.sleep(dur)
            self.house_light.off()
            print('  houselight should be OFF')
            time.sleep(dur)
            self.house_light.on()
            auto['house_light'] = 'PASS'
        except Exception as e:
            auto['house_light'] = 'FAIL (%s)' % e
        print('  house_light: %s' % auto['house_light'])

       # print('Testing RGB cue light...')
       # try:
       #     for color_fn, label in [(self.cue.red, 'red'), (self.cue.green, 'green'), (self.cue.blue, 'blue')]:
       #         print('  cue -> %s' % label)
       #         color_fn()
       #         time.sleep(dur)
       #    self.cue.off()
       #     auto['cue_light'] = 'PASS'
       # except Exception as e:
       #     auto['cue_light'] = 'FAIL (%s)' % e
       # print('  cue_light: %s' % auto['cue_light'])

        for port, name in [(self.left, 'left'), (self.center, 'center'), (self.right, 'right')]:
            print('Testing %s LED...' % name)
            try:
                port.on()
                time.sleep(dur)
                port.off()
                time.sleep(0.5)
                auto['%s_LED' % name] = 'PASS'
            except Exception as e:
                auto['%s_LED' % name] = 'FAIL (%s)' % e
            print('  %s_LED: %s' % (name, auto['%s_LED' % name]))

        print('Testing hopper...')
        try:
            self.reward(value=dur)
            auto['hopper'] = 'PASS'
        except Exception as e:
            auto['hopper'] = 'FAIL (%s)' % e
        print('  hopper: %s' % auto['hopper'])

        print('Testing speaker...')
        try:
            self.speaker.queue('/home/pi/test.wav')
            self.speaker.play()
            time.sleep(1.0)
            self.speaker.stop()
            auto['speaker'] = 'PASS'
        except Exception as e:
            auto['speaker'] = 'FAIL (%s)' % e
        print('  speaker: %s' % auto['speaker'])

        # ------------------------------------------------------------------
        # Phase 2: user confirmation
        # ------------------------------------------------------------------
        print('\n=== Phase 2: User confirmation ===')

        #check the houselight
        print('\nHouse light:')
        self.house_light.off()
        confirmed['house_light_off'] = 'CONFIRMED' if confirm('House light OFF -- confirm?') else 'FAIL'
        self.house_light.on()
        confirmed['house_light_on'] = 'CONFIRMED' if confirm('House light ON -- confirm?') else 'FAIL'

       # print('\nRGB cue light:')
       # for color_fn, label in [(self.cue.red, 'red'), (self.cue.green, 'green'), (self.cue.blue, 'blue')]:
       #     color_fn()
       #     confirmed['cue_%s' % label] = 'CONFIRMED' if confirm('Cue light %s -- confirm?' % label) else 'FAIL'
       # self.cue.off()

        #check the peck ports
        for port, name in [(self.left, 'left'), (self.center, 'center'), (self.right, 'right')]:
            print('\n%s peck port:' % name.capitalize())
            port.on()
            confirmed['%s_LED' % name] = 'CONFIRMED' if confirm('%s LED ON -- confirm?' % name.capitalize()) else 'FAIL'
            port.off()
            print('  Break the %s beam now (10 second timeout)...' % name)
            deadline = time.time() + 10.0
            detected = False
            while time.time() < deadline:
                if port.status():
                    detected = True
                    break
                time.sleep(0.05)
            if detected:
                confirmed['%s_IR' % name] = 'CONFIRMED'
                print('  %s IR: beam break detected' % name)
            else:
                confirmed['%s_IR' % name] = 'FAIL (no beam break detected)'
                print('  %s IR: timed out -- no beam break detected' % name)

        #check the  hopper
        print('\nHopper:')
        self.reward(value=dur)
        confirmed['hopper'] = 'CONFIRMED' if confirm('Hopper raised and lowered -- confirm?') else 'FAIL'

        #check the audio ouput
        print('\nSpeaker:')
        self.speaker.queue('/home/pi/test.wav')
        self.speaker.play()
        confirmed['speaker'] = 'CONFIRMED' if confirm('Is white noise playing? -- confirm to stop?') else 'FAIL'
        self.speaker.stop()

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        all_passed = True
        print('\n=== Panel test results ===')
        print('\n  Autonomous:')
        for component, result in auto.items():
            print('    %-20s %s' % (component, result))
            if not result.startswith('PASS'):
                all_passed = False
        print('\n  User confirmed:')
        for component, result in confirmed.items():
            print('    %-20s %s' % (component, result))
            if result != 'CONFIRMED':
                all_passed = False
        print('\n  Overall: %s' % ('PASS' if all_passed else 'FAIL'))
        print('==========================\n')

        return all_passed
