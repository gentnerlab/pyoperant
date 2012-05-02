import scipy

options = {}
options['stims'] = {
                   'a': 'JKseqv2_a.wav',
		           'b': 'JKseqv2_b.wav',
		 		   'c': 'JKseqv2_c.wav',
		           'd': 'JKseqv2_d.wav',
		           'e': 'JKseqv2_e.wav',
		           'f': 'JKseqv2_f.wav',
		           'g': 'JKseqv2_g.wav',
		           'h': 'JKseqv2_h.wav',
		           }

""" the first file is either GO or LEFT """
markov_files = {'L': 'JKseq_alpha930_n8.markov1',
                'R': 'JKseq_alpha930_inv_n8.markov1',
                }

models = []
for model in markov_files:
	models.append(scipy.genfromtxt('JKseq_alpha930_inv_n8.markov1',delimiter = ','))

options['models'] = {'L': models[0],
                     'R': models[1],}

options['strlen_min'] = 8
options['strlen_max'] = 8

options['isi_mean'] = 0.1 #seconds
options['isi_stdev'] = 0.015 

options['variable_ratio'] = 3
options['feed_dur'] = 3.0
options['timeout_dur'] = 5.0
options['response_win'] = 2.0

options['light_schedule'] = 'sun'




