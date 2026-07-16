# -*- coding: utf-8 -*-
"""
Created on Tue Jan 19 16:17:02 2016

@author: michael
"""

#!/usr/bin/env python

import os, sys, random, csv, shutil, string
import numpy as np
from pyoperant import utils, components, local, hwio
from pyoperant.behavior import two_alt_choice
import copy
import string
import pandas as pd

try:
    import simplejson as json
except ImportError:
    import json
    #json needs to have a 

class TargObjObj(two_alt_choice.TwoAltChoiceExp):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
      
      super(TargObjObj, self).__init__(*args, **kwargs)
      self.starting_params = copy.deepcopy(self.parameters) # save beginning parameters to reset each session
      self.clear_song_folder() # removes everything in the current song folder      
      self.get_conditions()  # get conditions for trial in block (e.g. ABA, BAB, BBA, ...)
      self.get_motifs()  # builds specific motif sequences (e.g. [A12, B1, A40])
      self.build_wavs() # build wav files from the generated sequences 
    
    def clear_song_folder(self):
      """ 
      deletes everything in the song folder
      """
      folder = self.parameters["stim_path"]+"/Generated_Songs/"
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
        generates a random 100 trial block (ABA, AAB, BAB, etc)
        """
        self.trial_types = np.matrix('0; 1'); #
        self.trials=[]    
        for i in xrange(100):    
            self.trials.append(random.randrange(0,2,1))    
        self.trial_output = [self.parameters["category_conditions"][i]["class"] for i in self.trials]

    def get_motifs(self): 
        """ 
        2. generate specific stim sequence e.g. [A12, B1, A40]
        """
        self.song_motifs = []
        molen = self.parameters["current_available_motifs"]
        stims = self.parameters["stims"]
        repeats = self.parameters["repeats"]
        motif_seq = self.trials        

      	for i in motif_seq:
          thisstim = []

          first_motif = int(random.randrange(0,molen,1))
          second_motif = int(np.random.uniform(float(first_motif)-3, float(first_motif+3)))%molen
          while second_motif == first_motif:
            second_motif = int(np.random.uniform(float(first_motif)-3, float(first_motif+3)))%molen

          # if self.parameters["curblock"] == "pos1":
          #   thisstim.append((self.parameters["lowtones"][int(np.random.uniform(0,12))], 0))
          # if self.parameters["curblock"] == "pos2":
          #   thisstim.append((self.parameters["hightones"][int(np.random.uniform(0,12))], 0))

          [thisstim.append((stims[str(first_motif)], 0)) for thing in xrange(repeats)]

          if (i == 1 and self.parameters["curblock"] == "pos1") or (i == 0 and self.parameters["curblock"] == "pos2"):
            #if match and pos1 is target or nonmatch and pos2 is target
            [thisstim.append((stims[str(first_motif)], 0)) for thing in xrange(repeats)]
            [thisstim.append((stims[str(second_motif)], 0)) for thing in xrange(repeats)]
          elif (i == 1 and self.parameters["curblock"] == "pos2") or (i == 0 and self.parameters["curblock"] == "pos1"):
            #if match and pos2 is target or nonmatch and pos1 is target
            [thisstim.append((stims[str(second_motif)], 0)) for thing in xrange(repeats)]
            [thisstim.append((stims[str(first_motif)], 0)) for thing in xrange(repeats)]

          self.song_motifs.append(thisstim)

    def build_wavs(self):
        """ 
        Creates wav files for each trial and puts them in a destination folder
        """        
        for i,j in zip(self.song_motifs, self.trials): #number of trials per epoch
          #jitter = random.uniform(0.05,0.1)
          inputnames = ''.join(str(elem) for elem in [os.path.split(thing[0])[-1] for thing in i]) #generates a name that's just a string of the names of the files used in this seq.
          song_wav = utils.concat_wav(i,output_filename=str(self.parameters["stim_path"]+"/Generated_Songs/"+inputnames+".wav")) #generates wavs (hopefully)

          self.parameters["stims"][inputnames] = self.parameters["stim_path"]+"/Generated_Songs/"+inputnames+".wav"

          cur_dict = {}
          cur_dict["class"] = "L" if j==1 else "R"
          cur_dict["stim_name"] = inputnames
          self.parameters["block_design"]["blocks"]["default"]["conditions"].append(cur_dict)

    def session_post(self):
        """ 
        Closes out the sessions
        """
        self.parameters = copy.deepcopy(self.starting_params) # copies the original conditions every new session
        self.clear_song_folder() # removes everything in the current song folder      
        self.get_conditions()  # get conditions for trial in block (e.g. ABA, BAB, BBA, ...)
        self.get_motifs()  # builds specific motif sequences (e.g. [A12, B1, A40])
        self.build_wavs() # build wav files from the generated sequences
        self.log.info('ending session')
        self.trial_q = None
        return None
