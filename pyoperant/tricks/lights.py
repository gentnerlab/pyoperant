#!/usr/bin/python
from pyoperant import utils
from pyoperant.tricks import base

class Lights(base.BaseExp):
    """docstring for Lights"""
    def __init__(self,  *args, **kwargs):
        super(Lights, self).__init__(*args, **kwargs)
        pass

if __name__ == "__main__":

    cmd_line = utils.parse_commandline()
    parameters = cmd_line['config']

    from pyoperant.local import PANELS
    panel = PANELS[parameters['panel']]()

    exp = Lights(panel=panel,**parameters)
    exp.run()



