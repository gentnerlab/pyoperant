import os
from pyoperant import (configure, states, panels, behavior, stimuli, blocks, subjects)


def run(configuration_file):
    """ Run an experiment or set of experiments detailed in the configuration file """

    # Check for configuration file
    if not os.path.exists(configuration_file):
        raise IOError("Configuration file could not be found: %s" % configuration_file)

    # Load the configuration based on its extension
    extension = os.path.splitext(configuration_file)[1].lower()
    if extension == ".yaml":
        parameters = configure.ConfigureYAML(configuration_file)
    elif extension == ".json":
        parameters = configure.ConfigureJSON(configuration_file)
    else:
        raise ValueError("Configuration file must be either yaml or json")

    # Set up subject

    # Set up panel

    # Set up experiments

    # Set up stimlulus conditions

    # Set up blocks

    # Set up BlockHandler
