#!/usr/bin/python

from pyoperant import utils
from pyoperant.tricks import three_ac_matching, shape

class ThreeACMatchingExpShape(three_ac_matching.ThreeACMatchingExp):
    def __init__(self, *args, **kwargs):
        super(ThreeACMatchingExpShape, self).__init__(*args, **kwargs)
        self.shaper = shape.Shaper3AC(self.panel, self.log, self.parameters, self.log_error_callback)

    def run(self):

        for attr in self.req_panel_attr:
            assert hasattr(self.panel,attr)
        self.panel.reset()
        self.save()
        self.init_summary()

        self.log.info('%s: running %s with parameters in %s' % (self.name,
                                                                self.__class__.__name__,
                                                                self.snapshot_f,
                                                                )
                      )

        self.shaper.run_shape()
        utils.run_state_machine(start_in='idle',
                                error_state='idle',
                                error_callback=self.log_error_callback,
                                idle=self._run_idle,
                                sleep=self._run_sleep,
                                session=self._run_session)

if __name__ == "__main__":

    try: import simplejson as json
    except ImportError: import json


    from pyoperant.local import PANELS

    cmd_line = utils.parse_commandline()
    with open(cmd_line['config_file'], 'rb') as config:
            parameters = json.load(config)


    if parameters['debug']:
        print parameters
        print PANELS

    panel = PANELS[parameters['panel_name']]()

    exp = ThreeACMatchingExpShape(panel=panel,**parameters)
    exp.run()