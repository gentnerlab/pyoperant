# -*- coding: utf-8 -*-
"""
Created on Tue Jan 26 11:46:20 2016

@author: timsainb
"""

#!/usr/bin/env python

import os, sys, random, csv, shutil
import numpy as np
import datetime as dt
from pyoperant import utils, components, local, hwio
from pyoperant.behavior import two_alt_choice
# my imports
import scipy.io.wavfile as wav
from scikits.samplerate import resample

from scipy import stats

try:
    import simplejson as json
except ImportError:
    import json

class XYContext(two_alt_choice.TwoAltChoiceExp):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
      super(XYContext, self).__init__(*args, **kwargs)
      self.clear_song_folder() # removes everything in the current song folder      
      self.get_conditions()  # get conditions for trial in block (e.g. ABA, BAB, BBA, ...)
      self.get_motifs()  # builds specific motif sequences (e.g. [A12, B1, A40])
      self.build_wavs() # build wav files from the generated sequences 
      self.append_conditions_and_stims()
    
    def clear_song_folder(self):
      """ 
      deletes everything in the song folder
      """
      folder = 'Generated_Motifs/'
      for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
          if os.path.isfile(file_path):
              os.unlink(file_path)
          #elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception, e:
          print e
      
    def get_conditions(self):
        """
        1. Creates a PDF depending for each trial type (e.g. P(ABA) = .4)
        2. generates a random 100 trial block (ABA, AAB, BAB, etc)
        """
        self.trial_types = np.matrix('1 1 1; 2 2 2; 1 1 2; 2 2 1; 1 2 1; 2 1 2; 1 2 2; 2 1 1'); # 2 = B 1 = A
        # Set probabilities of song based on trial conditions        
        if self.parameters["trial_condition"] == "equal": 
          song_probs = [.125] * 8;
        else:
          song_probs = (.40, .40, .10, .10, .40, .40, .10, .10);
        # Define a PDF for DRVs
        drv_cond = stats.rv_discrete(name='custm', values=(np.arange(8), song_probs))
        #plt.plot(np.arange(8),song_probs)
        self.trials = drv_cond.rvs(size=100) # generate trials from drv distribution
        self.trial_seq = np.reshape(self.trial_types[self.trials], (300))-1 # the sequence of trials (e.g. 1 1 2; 2,1,1)
        self.trial_output = [self.parameters["category_conditions"][i]["class"] for i in self.trials]

    def get_motifs(self): 
        """ 
        1. build a library of probabilities for each stimuli (e.g. A1 = .04, A2 = .1)
        2. generate specific stim sequence e.g. [A12, B1, A40]
        """
        motifs_dist = np.linspace(1, 46, 46)
        if self.parameters["distribution_type"] == "bimodal": 
          motif_probs = stats.norm.pdf(motifs_dist, loc = 23, scale = 6)
        else:
          motif_probs = np.asarray([float(1)/46] * 46)
        #plt.plot(motifs_dist,motif_probs)
        drv_motifs = stats.rv_discrete(name='custm', values=(motifs_dist, motif_probs))
        motif_seq = drv_motifs.rvs(size=300)
        motif_seq = 47*self.trial_seq+ motif_seq + 1 
        self.song_motifs = np.reshape(motif_seq, (100, 3)) # [38 20 86]; [37 79 41], etc  
        
    def append_conditions_and_stims(self):
        """
           1. Append new conditions (e.g. 33200511) to conditions in self.parameters
           2. Append new stims (e.g. 33200511 and 33200511.wav) to stims in self.parameters
        """
        for i in xrange(len(self.song_motifs)):
          cur_song = [str(self.song_motifs[i,0]).zfill(2) +str(self.song_motifs[i,1]).zfill(2) +str(self.song_motifs[i,2]).zfill(2)]
          # apply i/o to conditions list
          cur_dict = {}
          cur_dict[unicode("class", "utf-8")] = self.trial_output[i]
          cur_dict[unicode("stim_name", "utf-8")] = unicode(cur_song[0], "utf-8")
          self.parameters["block_design"]["blocks"]["default"]["conditions"].append(cur_dict)   
          # apply new inputs to stims
          self.parameters["stims"][unicode(cur_song[0], "utf-8")] = unicode('Generated_Motifs/'+[cur_song[0]+'.wav'][0], "utf-8")              
    
    def build_wavs(self):
        """ 
        Creates wav files for each trial and puts them in a destination folder        
        """

        for i in xrange(100):
          cur_song = [str(self.song_motifs[i,0]).zfill(2) +str(self.song_motifs[i,1]).zfill(2) +str(self.song_motifs[i,2]).zfill(2)]
          motif1_wav = wav.read(str(self.parameters["stims"][str(self.song_motifs[i,0])]))          
          motif2_wav = wav.read(str(self.parameters["stims"][str(self.song_motifs[i,1])]))          
          motif3_wav = wav.read(str(self.parameters["stims"][str(self.song_motifs[i,2])]))          
          song_wav = np.concatenate((motif1_wav[1],motif2_wav[1], motif3_wav[1]))
          
          if self.parameters["Machine"] == "Vogel":
            input_fr = 48000 # base sampling rate            
            output_fr = 44100 # new sampling rate
            song_wav = utils.resampleAudio(song_wav, input_fr, output_fr);
            wav.write("Generated_Motifs/"+str(cur_song[0])+".wav", output_fr, song_wav)
          else:
            wav.write("Generated_Motifs/"+str(cur_song[0])+".wav", motif1_wav[0], song_wav)
          
