import os
import csv
import logging
logger = logging.getLogger(__name__)


class Subject(object):
    """ Class which holds information about the subject currently running the
    experiment

    Parameters
    ----------
    name: string
        The name of the subject
    filename: string
        The name of the output file. The extension is used to determine the
        datastore type.

    Attributes
    ----------
    name: string
        The name of the subject
    filename: string
        The name of the output file
    datastore: Store object instance
        The datastore object in use

    Methods
    -------
    create_datastore(fields)
        Creates a datastore according to filename's extension
    store_data(trial)
        Stores a trial's data in the datastore
    """

    def __init__(self, name=None, filename=""):

        logger.debug("Creating subject object for %s" % name)
        self.name = name
        self.filename = filename
        logger.info("Created subject object with name %s" % self.name)
        self.datastore = None

    def create_datastore(self, fields):
        """ Creates a datastore object to store trial data

        Parameters
        ----------
        fields: list
            A list of field names to store from the trial object

        Returns
        -------
        bool
            True if the creation was successful

        Raises
        ------
        ValueError
            If filename extension is of unknown type
        """
        ext = os.path.splitext(self.filename)[1].lower()
        if ext == ".csv":
            self.datastore = CSVStore(fields, self.filename)
        else:
            raise ValueError("Extension %s is of unknown type" % ext)

        logger.info("Created datastore %s for subject %s" % (self.datastore,
                                                             self.name))

        return True

    def store_data(self, trial):
        """ Stores the trial data in the datastore

        Parameters
        ----------
        trial: instance of Trial
            The trial to store. It should have all fields used in creation of
            the datastore as attributes or annotations.

        Returns
        -------
        bool
            True if store succeeded
        """
        trial_dict = {}
        for field in self.datastore.fields:
            if hasattr(trial, field):
                trial_dict[field] = getattr(trial, field)
            elif field in trial.annotations:
                trial_dict[field] = trial.annotations[field]
            else:
                trial_dict[field] = None

        logger.debug("Storing data for trial %d" % trial.index)
        return self.datastore.store(trial_dict)


class CSVStore(object):
    """ Class that wraps storing trial data in a CSV file

    Parameters
    ----------
    fields: list
        A list of columns for the CSV file
    filename: string
        Full path to the csv file. Appends to the file if it already exists.

    Attributes
    ----------
    fields: list
        A list of columns for the CSV file
    filename: string
        Full path to the csv file

    Methods
    -------
    store(data)
        Appends data to the CSV file
    """
    def __init__(self, fields, filename):

        self.filename = filename
        self.fields = fields

        with open(self.filename, 'ab') as data_fh:
            trialWriter = csv.writer(data_fh)
            trialWriter.writerow(self.fields)

    def __str__(self):

        return "CSVStore: filename = %s, fields = %s" % (self.filename,
                                                         ", ".join(self.fields))

    def store(self, data):
        """ Appends the data to the CSV file

        Parameters
        ----------
        data: dictionary
            The data to store. The keys should match the fields specified when
            creating the CSVStore.

        Returns
        -------
        bool
            True if store succeeded
        """

        with open(self.filename, 'ab') as data_fh:
            trialWriter = csv.DictWriter(data_fh,
                                         fieldnames=self.fields,
                                         extrasaction='ignore')
            trialWriter.writerow(data)

        return True
