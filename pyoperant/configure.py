import os


class ConfigureJSON(object):

    @classmethod
    def load(cls, config_file):
        """ Load experiment parameters from a JSON configuration file

        Parameters
        ----------
        config_file: string
            path to a JSON configuration file

        Returns
        -------
        dictionary (or list of dictionaries) of parameters to pass to a behavior
        """
        try:
            import simplejson as json
        except ImportError:
            import json

        with open(config_file, 'rb') as config:
            parameters = json.load(config)

        return parameters

    @staticmethod
    def save(parameters, filename, overwrite=False):
        """ Save a dictionary of parameters to an experiment JSON config file

        Parameters
        ----------
        parameters: dictionary
            experiment parameters
        filename: string
            path to output file
        overwrite: bool
            whether or not to overwrite if the output file already exists
        """
        try:
            import simplejson as json
        except ImportError:
            import json

        if os.path.exists(filename) and (overwrite is False):
            raise IOError("File %s already exists! To overwrite, set overwrite=True" % filename)

        with open(filename, "w") as json_file:
            json.dump(parameters,
                      json_file,
                      sort_keys=True,
                      indent=4,
                      separators=(",", ":"))


class ConfigureYAML(object):
    """ Configuration using YAML files. Thanks to pyyaml (http://pyyaml.org/wiki/PyYAMLDocumentation), this type of configuration file can be very flexible. It supports multiple experiments in the form of multiple documents in one file. It also allows for expressing native python objects (including custom classes) directly in the configuration file.
    """

    @classmethod
    def load(cls, config_file):
        """ Load experiment parameters from a YAML configuration file

        Parameters
        ----------
        config_file: string
            path to a YAML configuration file

        Returns
        -------
        dictionary (or list of dictionaries) of parameters to pass to a behavior
        """
        try:
            import yaml
        except ImportError:
            raise ImportError("Pyyaml is required to use a .yaml configuration file")

        parameters = list()
        with open(config_file, "rb") as config:
            for val in yaml.load_all(config):
                parameters.append(val)

        if len(parameters) == 1:
            parameters = parameters[0]

        return parameters

    @staticmethod
    def save(parameters, filename, overwrite=False):
        """ Save a dictionary of parameters to an experiment YAML config file

        Parameters
        ----------
        parameters: dictionary
            experiment parameters
        filename: string
            path to output file
        overwrite: bool
            whether or not to overwrite if the output file already exists
        """
        try:
            import yaml
        except ImportError:
            raise ImportError("Pyyaml is required to use a .yaml configuration file")

        if os.path.exists(filename) and (overwrite is False):
            raise IOError("File %s already exists! To overwrite, set overwrite=True" % filename)

        with open(filename, "w") as yaml_file:
            yaml.dump(parameters, yaml_file,
                      indent=4,
                      explicit_start=True,
                      explicit_end=True)


# ## What is this??
# class ConfigurableYAML(type):
#
#     def __new__(cls, *args, **kwargs):
#
#         ConfigureYAML.constructors.append(cls)
#         return super(ConfigureableYAML, cls, *args, **kwargs)
