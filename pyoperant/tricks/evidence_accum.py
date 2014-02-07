#!/usr/bin/python

import os, sys, random, csv, time
import numpy as np
import datetime as dt
from pyoperant import utils, components, local, hwio
from pyoperant.tricks import two_alt_choice

try:
    import simplejson as json
except ImportError:
    import json

class NumpyAwareJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
                return obj.tolist()
        return json.JSONEncoder.default(self, obj)


class EvidenceAccumExperiment(two_alt_choice.TwoAltChoiceExp):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(EvidenceAccumExperiment, self).__init__(*args, **kwargs)
        self.build_transition_matrices()

    def save(self):
        self.snapshot_f = os.path.join(self.parameters['experiment_path'], self.timestamp+'.json')
        with open(self.snapshot_f, 'wb') as config_snap:
            json.dump(self.parameters,
                      config_snap,
                      sort_keys=True,
                      indent=4,
                      cls=NumpyAwareJSONEncoder)

    def build_transition_matrices(self):
        """run through the transitions for each stimulus and generate transition matrixes"""
        n = len(self.parameters['stim_map'])

        for stim_class, class_params in self.parameters['classes'].items():
            arr = np.zeros((n,n),np.float_)
            for a,b in class_params['transitions']:
                arr[a,b] = 1.0

            self.parameters['classes'][stim_class]['evidence_arrays'] = arr
            self.log.debug('added class %s evidence array %s' % (stim_class,arr))

        stim_classes = self.parameters['classes'].keys()
        assert len(stim_classes) == 2

        for this_class in stim_classes:
            other_class = [cl for cl in stim_classes if (cl != this_class)][0]
            trans = self.parameters['odds'] \
                  * self.parameters['classes'][this_class]['evidence_arrays'] \
                  + self.parameters['classes'][other_class]['evidence_arrays']
            trans[0,1:] = 1.0
            trans = np.cumsum(trans,axis=1)
            trans = trans / trans[:,-1][:,None] # I don't get why it suddenly works to append '[:,None]'
            self.parameters['classes'][this_class]['transition_cdf'] = trans
            self.log.debug('added class %s transition cdf %s' % (this_class, trans))

    def get_stimuli(self,trial_class):
        """ take trial class and return a tuple containing the stimulus event to play and a list of additional events

        """

        input_files = []
        motif_ids = []

        # use transition CDF to get iteratively get next motif id
        mid = 0
        for pos in range(self.parameters['strlen_max']):
            mid = (self.parameters['classes'][trial_class]['transition_cdf'][mid] < random.random()).sum()
            motif_ids.append(mid)
        assert len(motif_ids) == self.parameters['strlen_max']

        motifs = [self.parameters['stim_map'][mid] for mid in motif_ids]

        motif_isi = [max(random.gauss(self.parameters['isi_mean'], self.parameters['isi_stdev']),0.0) for mot in motifs]
        motif_isi[-1] = 0.0

        input_files = [(self.parameters['stims'][motif_name], isi) for motif_name, isi in zip(motifs,motif_isi)]
        filename =  os.path.join(self.parameters['stim_path'], ''.join(motifs) + '.wav')
        stim, epochs = utils.concat_wav(input_files,filename)

        for ep in epochs:
            self.log.debug('old epoch.name: %s' % ep.name)
            for stim_name,f_name in self.parameters['stims'].items():
                if ep.name == f_name:
                    ep.name = stim_name
            self.log.debug('new epoch.name: %s' % ep.name)

        stim.name = ''.join(motifs)

        return stim, epochs

    def trial_pre(self):
        ''' this is where we initialize a trial'''
        # make sure lights are on at the beginning of each trial, prep for trial

        self.new_trial()

        self.this_trial = self.trials[-1]
        motifs = [m for m in self.this_trial.events if (m.label=='motif')]
        min_motif = motifs[self.parameters['strlen_min']-1]
        self.this_trial.annotate(min_wait=min_motif.time+min_motif.duration)
        max_wait = self.this_trial.stimulus_event.duration + self.parameters['response_win']
        self.this_trial.annotate(max_wait=max_wait)
        self.log.debug('created new trial')
        return 'main'

    def analyze_trial(self):
        '''after the trial is complete, perform additional analyses that will be saved'''

        for event in self.this_trial.events:
            event.time += self.this_trial.stimulus_event.time

        # determine the string of motifs the bird heard
        num_mots = 0
        for ev in list(self.this_trial.events):
            if (ev.label=='motif'):
                if (self.this_trial.rt > ev.time) or (self.this_trial.response == 'none'):
                    num_mots += 1
                else:
                    self.this_trial.events.remove(ev) # get rid of motif events the bird didn't hear

        self.this_trial.stimulus = self.this_trial.stimulus[:num_mots]



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

    exp = EvidenceAccumExperiment(panel=panel,**parameters)
    exp.run()


