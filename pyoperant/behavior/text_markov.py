#!/usr/bin/env python
import glob
import os, sys, random, csv, shutil
import numpy as np
import datetime as dt
from pyoperant import utils, components, local, hwio
from pyoperant.behavior import two_alt_choice
# my imports
import scipy.io.wavfile as wav
from scipy import stats
import copy
import pandas as pd
from pyoperant.errors import EndSession, EndBlock
import math
import types
import time
import cPickle
sys.path.append('/home/pi/')
from sparray import *
import sys
from pyoperant import components, utils, reinf, queues



try:
    import simplejson as json
except ImportError:
    import json

class text_markov(two_alt_choice.TwoAltChoiceExp):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
      super(text_markov, self).__init__(*args, **kwargs)

      #self.panel.speaker.interface.callback = self.callback # add a callback to audio output
      self.fields_to_save += ['order', 'sequence'] # add information about the trial
      self.make_data_csv() # recreate titles for csv (to include scale, etc)
      self.starting_params = copy.deepcopy(self.parameters) # save beginning parameters to reset each session
      self.pre_trial_cue()


    def pre_trial_cue(self):
        """
        Before each block, build a distribution
        """
        clear_song_folder(folder=self.parameters["stim_path"]) # removes everything in the current song folder
        self.determine_markov_orders_to_use() # look through past blocks and determine what Markov orders to play back
        self.generate_sequences() # both generates markov sequences and samples from real sequences

    def determine_markov_orders_to_use(self):
        """
        Stored in the json we have parameters:
           num_blocks_above_thresh: how many previous blocks in a row have been above some threshold percentage for Performance
           current_order: the current highest order of the markov model (potentially updated here)
           pct_markov: what percent of trials to make Markov generated
           pct_cur_model: the percentage of Markov trials using the current (highest order) model.
        E.g. if pct_cur_model is .5 and the current order is 3, the full model will use 50% 3rd order,
        25% 2nd order, 12.5 % first order and 12.5% 0th order - default to 1, meaning that all trials are the highest order model


        Returns a list of 100 trials markov order, vs full sequences. e.g. [0,-1,0,1,0,-1,1], where -1 is full
        """
        self.current_order = self.parameters["current_order"]
        # Determine the probabilities of each order model being played back
        order_prob = []
        for order in np.arange(self.current_order + 1)[::-1]: # loop through each markov orders
            remaining_prob = 1. - np.sum(order_prob)
            if order ==0:
                order_prob.append(remaining_prob) # append all of the remaining probability to the lowest order
            else:
                order_prob.append(remaining_prob * self.parameters["pct_cur_model"])

        order_prob = order_prob[::-1] # flip back to go from 0th to nth order
        #print(np.arange(self.current_order + 1), order_prob)

        self.trial_order_list = [] # a list of the Markov orders to use for the experiment
        for trial_i in range(self.parameters["trials_per_block"]):
            if np.random.binomial(1, .5): # flip a coin for markov vs readline
                self.trial_order_list.append(-1)
            else:
                # determine markov order and append to trial_order_list
                self.trial_order_list.append(np.random.choice(np.arange(self.current_order+1), p=order_prob))
        #print(order_prob)

    def generate_sequences(self):
        """
        1. Load up Markov models (up to the corresponding order)
        2. Walk through each trial and generate a sequence of length markov_seq_len
        """
        # Load up Markov models - up to the max used
        MMs = [load_MMs(self.parameters['experiment_path']+'/MarkovModels/'+str(order)+'.pickle') for order in np.arange(self.current_order + 1)]
        # Load up true sequences
        sentences = np.load(self.parameters['experiment_path']+ '/sentences_numerical.npy')
        # compute the distribution of true sequence lengths
        sentence_lens = [len(i) for i in sentences]
        #self.syll_time_lens = [] # a list holding for each sequence the lengths of the corresponding syllables, so that we can know at what time each syllable occurs
        #self.sequences = []
        for trial_num, order in enumerate(self.trial_order_list):
            stim_dict = {} # a dictionary that holds onto stimuli info. eg. {"class": "L", "stim_name": "a"},
            if np.random.binomial(1, self.parameters['prob_fixed_example']): # at some probability, make the model use a fixed example
                    # Choose which fixed example
                    if order == -1: # if this is a true sentence
                        stim_dict[unicode("class", "utf-8")] =  self.parameters['reinforce_real_side']
                        seq = self.parameters['real_exemplars'][np.random.choice(self.parameters['n_exemplars'])] # chose a pregenerated real sequence
                    else:
                        stim_dict[unicode("class", "utf-8")] = self.parameters['reinforce_markov_side']
                        seq = self.parameters['generated_exemplars'][np.random.choice(self.parameters['n_exemplars'])]  # choose a pregenerated fake sequence
            else:
                if order == -1: # if this is a true sentence
                    stim_dict[unicode("class", "utf-8")] =  self.parameters['reinforce_real_side'] # either L or R, this represents the reinforcement
                    seq = sentences[np.random.choice(len(sentences))]
                else: # if this is a Markov generated sentence
                    stim_dict[unicode("class", "utf-8")] = self.parameters['reinforce_markov_side']
                    sequence_length = sentence_lens[np.random.choice(len(sentence_lens))] # length of the sentence to be generated
                    seq = generate_MM_seq(sequence_length, MMs[:order+1], self.parameters['n_symbols'], use_tqdm=False)
            seq_str = '-'.join([str(i) for i in seq]) # create a string representing the sequence
            stim_dict[unicode("stim_name", "utf-8")] = seq_str
            stim_dict[unicode("seq", "utf-8")] = list(seq)
            stim_dict[unicode("order", "utf-8")] = str(order)
            #self.sequences.append(seq)
            self.parameters["stims"][seq_str] = self.parameters["stim_path"] + str(trial_num) + '.wav'
            # generate the wav

            stim_dict[unicode("syll_time_lens", "utf-8")] = self.build_wav(seq, self.parameters["stim_path"] + str(trial_num) + '.wav')


            self.parameters["block_design"]["blocks"]["default"]["conditions"].append(stim_dict) # add to the list of stims

        #print(['seqs: ']+ [i[:5] for i in self.sequences[:3]])
        #print(self.parameters["block_design"]["blocks"]["default"]["conditions"][:3])


    def build_wav(self, seq, wav_name):
        """
        2. Create a list of the corresponding build_wavs and concatenate them (surrounded by an isi)
        3. Save wavs to stim folder
        """
        song_wav = [np.concatenate(
            [wav.read(self.parameters["experiment_path"]+"/stim_lib/1201_bout_"+self.parameters["text_to_syllable"][self.parameters["num_to_char"][str(num)]]+".wav")[1] ,
            np.zeros(int(self.parameters["rate"]*self.parameters["isi"]))
            ]) for num in seq]
        syll_time_lens = [0] + list(np.cumsum([len(i)/float(self.parameters["rate"]) for i in song_wav]))+[100000]
        wav.write(wav_name,self.parameters["rate"],np.concatenate(song_wav).astype('int16'))
        return syll_time_lens

    def session_post(self):
        """ Closes out the sessions
        """
        self.parameters = copy.deepcopy(self.starting_params) # copies the original conditions every new session

        self.pre_trial_cue() # build a new trial

        self.log.info('ending session')
        self.trial_q = None
        # get a new distrubtion ready for the next session
        ###### NEEDS TO BE FIXED ######
        #self.determine_stim_distribution() # determines distribution scale for motifs
        return None

    def run_trial(self):
        self.trial_pre() # adds time to log ##### WILL NEED TO CHANGE MIN_WAIT, MAX_WAIT

        self.stimulus_pre() # Poll for center peck, append info, turn on peck ports

        self.stimulus_main() # repeatedly play stimulus

        self.response_post() # turns off ports

        self.consequence_pre()
        self.consequence_main()
        self.consequence_post()

        self.trial_post()


    def stimulus_pre(self):
        """
        Prepares stimuli to be presented
        ADDED: turn on peck ports
        """

        # wait for bird to peck
        self.log.debug("presenting stimulus %s" % self.this_trial.stimulus)
        self.log.debug("from file %s" % self.this_trial.stimulus_event.file_origin)
        self.log.debug('waiting for peck...')
        self.panel.center.on()
        trial_time = None
        #print(self.check_session_schedule())
        while trial_time is None:

            if self.check_session_schedule()==False:
                self.panel.center.off()
                self.panel.speaker.stop()
                self.update_adaptive_queue(presented=False)
                raise EndSession
            else:
                trial_time = self.panel.center.poll(timeout=60.0)

        self.this_trial.time = trial_time
        self.this_trial.sequence = self.this_trial.annotations['seq']#self.sequences[self.this_trial.index]
        self.this_trial.order = self.this_trial.annotations['order'] #self.trial_order_list[self.this_trial.index]
        self.this_trial.syll_time_lens = self.this_trial.annotations['syll_time_lens'] #self.trial_order_list[self.this_trial.index]
        #print(vars(self.this_trial))
        #print(self.this_trial.sequence)
        #print(self.this_trial.index)

        #print('stim_name: ' + ''.join([self.parameters["num_to_char"][str(i)] for i in self.this_trial.annotations['stim_name'].split('-')]))
        #print('sequence: ' + ''.join([self.parameters["num_to_char"][str(num)] for num in self.this_trial.sequence]))
        self.log.info('sequence: ' + ''.join([self.parameters["num_to_char"][str(num)] for num in self.this_trial.sequence]))

        #print(breakme)
        self.panel.center.off()
        self.this_trial.events.append(utils.Event(name='center',
                                                  label='peck',
                                                  time=0.0,
                                                  )
                                            )

        # record trial initiation
        self.summary['trials'] += 1
        self.summary['last_trial_time'] = self.this_trial.time.ctime()
        self.log.info("trial started at %s" % self.this_trial.time.ctime())

        #print(vars(self.this_trial))
        #self.this_trial.scale = self.scale # set distribution scale each trial (so that the output can see it)
        #self.this_trial.left_pecks = 0
        #self.this_trial.right_pecks = 0
        #self.this_trial.center_pecks = 0
        #self.log.debug("scale: %s" % self.scale)


    def stimulus_main(self):
        """
        Continuously plays stimulus until the correct port port is pecked
        """
        self.log.debug("stimulus main")
        self.this_trial.response = 'none'
        # the length of the stimulus in seconds
        stim_length_s = self.this_trial.stimulus_event.annotations['annotations']['nframes'] / \
            float(self.this_trial.stimulus_event.annotations['annotations']['framerate'])

        self.stim_start = dt.datetime.now()
        wait_period = .0075 # number of seconds to wait between checking ports
        self.this_trial.stimulus_event.time = (self.stim_start - self.this_trial.time).total_seconds() # Not sure what this does...
        self.this_trial.correct = False #### Make sure this is OK with no response trials
        self.this_trial.incorrect = False
        self.this_trial.early_end = False

        self.panel.speaker.queue(self.this_trial.stimulus_event.file_origin) # que stimulus
        self.panel.speaker.play() # play stimulus
        #self.log.info(self.parameters["num_to_char"][str(self.this_trial.sequence[cur_sym])])

        # wait to start checking ports until a threshold time is set
        #cur_sym = 0 # this is for printing out one symbol at a time
        while True:
            if ( dt.datetime.now() - self.stim_start).total_seconds() > self.parameters["min_seconds_before_peck"]:
                """if (((dt.datetime.now()- self.stim_start).total_seconds() > self.this_trial.syll_time_lens[cur_sym]) \
                    & (cur_sym<len(self.this_trial.sequence))):
                    #sys.stdout.write(self.parameters["num_to_char"][str(self.this_trial.sequence[cur_sym])])
                    #sys.stdout.flush()
                    cur_sym +=1"""
                for class_, port in self.class_assoc.items():
                    port.on() # turns on lights
                break
            time.sleep(.1)

        # check ports until n_seconds after the stimuli stops

        while ( dt.datetime.now()- self.stim_start).total_seconds() - stim_length_s < self.parameters["max_seconds_after_stim"]:
            """if (((dt.datetime.now()- self.stim_start).total_seconds() > self.this_trial.syll_time_lens[cur_sym]) \
                & (cur_sym<len(self.this_trial.sequence))):
                #sys.stdout.write(self.parameters["num_to_char"][str(self.this_trial.sequence[cur_sym])])
                #sys.stdout.flush()
                cur_sym +=1"""
            time.sleep(wait_period)
            self.callback()
            # If the bird pecks, end the trial
            if self.this_trial.correct | self.this_trial.incorrect | self.this_trial.early_end:
                try:
                    #print(self.panel.speaker)
                    #print(vars(self.panel.speaker))
                    self.panel.speaker.stop()
                except  IOError as ioerr:
                    self.log.error("IO Error: %s" % str(ioerr))
                    sys.exit(1)
                    raise
                return
        self.panel.speaker.stop()
        # If the playbacks go all the way through and no peck was made
        self.log.info('no response')
        return

    def callback(self):
        # callback exists in self.panel.speaker.interface

        for class_, port in self.class_assoc.items():

            if port.status():

                self.this_trial.response = class_

                self.this_trial.rt = (dt.datetime.now() - self.stim_start).total_seconds()
                self.summary['responses'] += 1
                response_event = utils.Event(name=self.parameters['classes'][class_]['component'],
                                             label='peck',
                                             time=self.this_trial.rt,
                                             )

                self.this_trial.events.append(response_event)
                self.log.info('response: %s' % (self.this_trial.response))

                if class_ == self.this_trial.class_:
                    self.this_trial.correct = True
                else:
                    self.this_trial.incorrect = True
                return

    def consequence_main(self):
        if (self.this_trial.response == 'none') | (self.this_trial.early_end):
            pass
        elif self.this_trial.correct == True:

            if self.parameters['reinforcement']['secondary']:
                secondary_reinf_event = self.secondary_reinforcement()
                # self.this_trial.events.append(secondary_reinf_event)

            if self.this_trial.type_ == 'correction':
                self._run_correction_reward()
            elif self.reinf_sched.consequate(trial=self.this_trial):
                self.reward_pre()
                self.reward_main() # provide a reward
                self.reward_post()
        elif self.this_trial.incorrect == True:
            if self.reinf_sched.consequate(trial=self.this_trial):
                self.punish_pre()
                self.punish_main()
                self.punish_post()

    def secondary_reinforcement(self,value=1.0):
        if "cue" in dir(self.panel):
            self.panel.cue.red()
            utils.wait(.05)
            self.panel.cue.off()
            self.panel.cue.red()
            utils.wait(.05)
            self.panel.cue.off()
            return
        else:
            return self.panel.center.flash(dur=value)


def context_probs(MM, context_list, n_elements):
    prob_dist = [MM[tuple([i for i in context_list] + [j])] for j in range(n_elements)]
    return np.array(prob_dist,dtype='float32')/np.sum(prob_dist)
def MM_make_prediction(prev_seq, MMs, n_elements):
    """ Make a prediction given a markov model
    continuously decrease the order of the markov model if the model has no experieces of a given context
    """
    order = len(MMs) -1
    for i in range(len(MMs)):
        num_sub = [len(prev_seq) if len(prev_seq) < (order) else (order)][0]
        if order == 0:
            context_list = []
        else:
            context_list = [n_elements for j in range((order) - num_sub)] + \
                [i for i in list(prev_seq[-num_sub:])]
        prob_next = context_probs(MMs[order], context_list, n_elements)
        if np.sum(prob_next) > 0:
            break
        order -=1
    return prob_next

def generate_MM_seq(sequence_length, MMs, n_elements, use_tqdm=True):
    """
    Generates a sequence of length `sequence_length` given a transition matrix
    """
    #print('prepping seq list')
    sequence = np.zeros(sequence_length)
    #print('prepping iter')
    seqlist = tqdm(range(sequence_length), leave=False) if use_tqdm else range(sequence_length)
    for i in seqlist:
        prediction = MM_make_prediction(prev_seq = np.array(sequence)[:i],
                                                  MMs = MMs,
                                                  n_elements = n_elements)
        sequence[i] = np.random.choice(len(prediction), p=prediction,
                                         size = 1)[0]
    return sequence.astype('int')

def change_json_parameter(file_location, param, value):
    """
    changes parameter on a JSON
    warning: Using this function will reorder your json.
    """
    jsonFile = open(file_location, "r")
    data = json.load(jsonFile)
    data[param] = value
    jsonFile = open(file_location, "w+")
    jsonFile.write(json.dumps(data, indent=4, sort_keys=True))
    jsonFile.close()

def find_json_param(file_location, param):
    """
    goes into a json a finds a parameter value
    """
    jsonFile = open(file_location, "r")
    data = json.load(jsonFile)
    param_value = data[param]
    return(param_value)


def clear_song_folder(folder= 'Generated_Songs/'):
  """
  deletes everything in the song folder
  """
  for the_file in os.listdir(folder):
    file_path = os.path.join(folder, the_file)
    #try:
    if os.path.isfile(file_path):
      os.unlink(file_path)
      #elif os.path.isdir(file_path): shutil.rmtree(file_path)
    #except Exception, e:
      #self.log.error(e)


def load_MMs(loc):
    with open(loc, 'rb') as f:
        return cPickle.load(f)


def save_MMs(MMs, loc):
    with open(loc, "wb") as f:
        cPickle.dump(MMs, f)
