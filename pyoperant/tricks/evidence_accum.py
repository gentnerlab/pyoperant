#!/usr/bin/python

import os, sys, random, csv, time
import numpy as np
import datetime as dt
from pyoperant import utils, components, local, hwio, experiment

try:
    import simplejson as json
except ImportError:
    import json


class EvidenceAccumExperiment(experiment.Experiment):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(EvidenceAccumExperiment, self).__init__(*args, **kwargs)

    def build_transition_matrices(self): 
        # run through the transitions for each stimulus and generate transition matrixes
        n = len(self.stim_map)
        self.evidence_arrays = {}
        for stim_class, class_params in self.parameters['classes'].items():
            arr = np.zeros((n,n),np.float_)
            for a,b in class_params['transitions']:
                arr[a,b] = 1.0

            self.parameters[this_class]['evidence_arrays'] = arr

        self.stim_classes = self.parameters['classes'].keys()
        assert len(self.stim_classes) == 2

        for this_class in self.parameters['classes'].keys():
            other_class = [cl for cl in self.stim_classes if cl is not this_class][0]
            trans = self.odds \
                  * self.parameters[stim_class]['evidence_arrays'][stim_class] \
                  + self.parameters[other_class]['evidence_arrays']
            trans[0,1:] = 1.0
            trans = np.cumsum(trans,axis=1)
            trans = trans / trans[:,-1][:,None] # I don't get why it suddenly works to append '[:,None]'
            self.parameters[this_class]['transition_cdf'] = trans

    def get_stimuli(self,trial_class):
        """ take trial class and return a tuple containing the stimulus event to play and a list of additional events

        """

        input_files = []
        motif_ids = []

        # use transition CDF to get iteratively get next motif id
        mid = 0
        for pos in range(self.strlen_max):
            mid = (self.parameters[trial_class]['transition_cdf'][mid] < random.random()).sum()
            motif_ids.append(mid)
        assert len(motif_ids) == self.strlen_max

        motifs = [self.stim_map[mid] for mid in motif_ids]

        motif_isi = [max(random.gauss(self.parameters['isi_mean'], self.parameters['isi_stdev']),0.0) for mot in motifs]
        motif_isi[-1] = 0.0

        input_files = [(self.stims[motif_name], isi) for motif_name, isi in zip(motifs,motif_isi)]
        filename =  os.path.join(self.stim_path, ''.join(motifs) + '.wav')
        stim, epochs = utils.concat_wav(input_files,filename)

        return stim, epochs


    def analyze_trial(self,trial):
        '''after the trial is complete, perform additional analyses that will be saved'''
        trial_stim.time = trial_stim.time + trial['stim_start']
        for motif in trial_motifs:
            motif.time = motif.time + trial['stim_start']

        # calculate the number of motifs the bird heard
        if trial['response'] == 'none':
            num_mots = len(trial_motifs)
        else:
            num_mots = 0
            for motif in trial_motifs:
                if trial['response_time'] > motif.time:
                    num_mots += 1
        # determine the string of motifs the bird heard
        trial['stim_motifs'] = trial_motifs[:num_mots]

        trial['stim_string'] = ''
        for motif in trial['stim_motifs']:
            trial['stim_string'] += next((name for name, wav in self.stims.iteritems() if wav == motif.name), '')

if __name__ == "__main__":

    cmd_line = utils.parse_commandline()
    parameters = cmd_line['config']

    from pyoperant.local import PANELS
    panel = PANELS[parameters['panel']]()

    exp = EvidenceAccumExperiment(panel=panel,**parameters)
    exp.run()


