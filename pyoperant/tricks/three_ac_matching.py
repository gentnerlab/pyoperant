import random, os
from pyoperant import utils
from pyoperant.tricks import two_alt_choice

class ThreeACMatchingExp(two_alt_choice.TwoAltChoiceExp):
    """docstring for ThreeACMatchingExp"""
    def __init__(self, *args, **kwargs):
        super(two_alt_choice.TwoAltChoiceExp, self).__init__(*args, **kwargs)
        self.num_stims = len(self.parameters['stims'].items())

    def get_stimuli(self, trial_class):
        """ take trial class and return a tuple containing the stimulus event to play and a list of additional events

        """
        mids = random.sample(xrange(self.num_stims), 3)
        if trial_class is "L":
            mids[2] = mids[0]
        elif trial_class is "R":
            mids[2] = mids[1]

        motif_names, motif_files = zip([self.parameters['stims'].items()[mid] for mid in mids])

        motif_isi = [max(random.gauss(self.parameters['isi_mean'], self.parameters['isi_stdev']), 0.0) for mot in motif_names]
        motif_isi[-1] = 0.0

        input_files = zip(motif_files, motif_isi)
        filename = os.path.join(self.parameters['stim_path'], ''.join(motif_names) + '.wav')
        stim, epochs = utils.concat_wav(input_files, filename)

        for ep in epochs:
            for stim_name, f_name in self.parameters['stims'].items():
                if ep.name in f_name:
                    ep.name = stim_name

        return stim, epochs

    def analyze_trial(self, trial):
        super(self, trial)
