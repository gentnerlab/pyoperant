import random

def random_queue(conditions,tr_max=100,weights=None):
    """ generator which randomly samples conditions

    Args:
       conditions (list):  The conditions to sample from. 
       weights (list of ints): Weights of each condition

    Kwargs:
       tr_max (int): Maximum number of trial conditions to generate. (default: 100)

    Returns:
        whatever the elements of 'conditions' are

    """
    if weights:
        conditions_weighted = []
        for cond,w in zip(conditions,weights):
            for ww in range(w):
                conditions_weighted += cond
        conditions = conditions_weighted

    tr_num = 0
    while tr_num < tr_max:
        yield random.choice(conditions)
        tr_num += 1

def block_queue(conditions,reps=1,shuffle=False):
    """ generate trial conditions from a block

    Args:
        conditions (list):  The conditions to sample from. 

    Kwargs:
        reps (int): number of times each item in conditions will be presented (default: 1)
        shuffle (bool): Shuffles the queue (default: False)

    Returns:
        whatever the elements of 'conditions' are

    """
    conditions_repeated = []
    for rr in range(reps):
        conditions_repeated += conditions
    conditions = conditions_repeated

    if shuffle:
        random.shuffle(conditions)
    
    for cond in conditions:
        yield cond

def staircase_queue(experiment,
                    start,
                    up=1,
                    down=3,
                    step=1.0,
                    min_val=None,
                    max_val=None,
                    tr_min=0,
                    tr_max=100,
                    reversals=None,
                    ):
    """ generates trial conditions for a staircase procedure

    This procedure returns values for each trial and assumes that larger values are
    easier. Thus, after a correct trial, the next value returned will be smaller and
    after incorrect trials, the next value returned will be larger. The magnitudes of
    these changes are down*step and up*step, respectively.

    Args:
        experiment (Experiment):  experiment object to keep track of last trial accuracy
        start (float/int): the starting value of the procedure

    Kwargs:
        up (int): number of steps to take after incorrect trial (default: 1)
        down (int): number of steps to take after correct trial (default: 3)
        step (float): size of steps (default: 1.0)
        shuffle (bool): Shuffles the queue (default: False)
        min_val (float): minimum parameter value to allow (default: None)
        max_val (float): maximum parameter value to allow (default: None)
        tr_min (int): minimum number of trials (default: 0)
        tr_max (int): maximum number of trials (default: 100)
    Returns:
        float

    """
    val = start
    # first trial, don't mess with checking
    yield val
    tr_num = 1
    nrev = 0
    going_up = True
    cont = True

    # subsequent trials
    while cont:
        
        last = experiment.trials[-1]

        # staircase logic
        if last.correct:
            chg = -1 * down
        else:
            chg = up
        val += float(step) * chg

        # check for reversal
        if last.correct==going_up: # checks if last trial's perf was consistent w/ trend
            nrev += 1
            going_up = not going_up

        # stop at max/min if we hit the rails
        if (max_val!=None) and (val > max_val):
            val = max_val
        elif (min_val!=None) and (val < min_val):
            val = min_val

        yield val

        # decide whether to stop iterating
        tr_num += 1
        if tr_num < tr_min:
            cont = True
        elif tr_num >= tr_max:
            cont = False
        elif nrev >= reversals:
            cont = False


def double_staircase_queue(self,stim_base,
                    svalues=[0,12,22,30,36,40,42,44,46,48,50,52,54,56,58,60,64,70,78,88,100],
                    rvalues=[0,24,76,100],
                    startL=20,
                    startR=0,
                    up=1,
                    down=1,
                    step=1,
                    min_val=0,
                    max_val=20,
                    tr_min=0,
                    tr_max=10000,
                    reversals=3
                    ):
    """ generates trial conditions for a double staircase procedure

    This procedure returns values for each trial and assumes that larger values are
    easier. Thus, after a correct trial, the next value returned will be harder and
    after incorrect trials, the next value returned will be easier. The magnitudes of
    these changes are down*step and up*step depending on which staircase you are on.  
    Two staircases will be going at once that start at oposing ends.
    The "Left" staircase starts from 100 and moves down with correct responses.
    The "Right" staircase starts from 0 and moves up with correct responses.


    Future coding ideas:
    subtract ValL and valR, divide by some interval to get adaptive step value
        -will need to generate stims on the fly and may want to do during ISI 

    Note:
    Will need to edit add_fields_to_save in config file to add relevant staircase variables - "type",tr_num","val","revL","revR"
    min_val should be equal to startR and max_val to startL

    Args:
        svalues (list): values possible to sample from during staircase
        rvalues (list): values possible to sample from on random interleaved trials
        experiment (Experiment):  experiment object to keep track of last trial accuracy
        start (float/int): the starting value of the procedure

    Kwargs:
        up (int): number of steps to take after incorrect trial (default: 1)
        down (int): number of steps to take after correct trial (default: 3)
        step (float): size of steps (default: 1.0)
        shuffle (bool): Shuffles the queue (default: False)
        min_val (float): minimum parameter value to allow (default: None)
        max_val (float): maximum parameter value to allow (default: None)
        tr_min (int): minimum number of trials (default: 0)
        tr_max (int): maximum number of trials (default: 100)
        reversals: number of reversals that both sides of staircase must meet before termination
        stim_base (str): first part of your stim name eg. "AE"
    Returns:
        float

    """
    tr_num = 0
    contL = False
    contR = False
    nrev = 0
    valL = startL
    valR = startR
    valLtemp = max(svalues)
    valRtemp = min(svalues)
    cont = True
#need to rename experiment trials to self.something- i forget what
#need to convert yield val into a conditions dictionary with string of stim name
#need to figure out where to pass in values- prob put in config file
#for right now it doesn't matter if choice of which staircase to use is random
    while cont:
        rand = random.randrange(4)
        if rand < 0:  #decide if on staircase or not- do i really need filler trials if R and L are interleaved?
            self.log.info('random stim')
            val = random.choice(rvalues)
            stim_name = "%s%s.wav" %(stim_base,val)
            if val > 49:
                port = "L"
            else:
                port = "R"
            cond = {"class":port,"stim_name":stim_name,"type":"random","tr_num":tr_num,"val":val,"rev":rev}
            yield cond # should i yield cond after deciding wether to stop iterating?
            tr_num += 1
        else:
            if rand < 2:
                nowL = False
            elif rand >= 2:
                nowL = True   

            if nowL:
                self.log.info('left staircase')
                # subsequent trials
                if contL:
                    last_num = lasttrialL - tr_num
                    last = self.trials[last_num]   
                    lasttrialL = tr_num
                    # staircase logic- reversed for LEFT stims
                    if last.correct == True:
                        chg = -1 * up
                    else:
                        chg = down
                    valL += step * chg
        

                    # stop at max/min if we hit the rails
                    if (max_val!=None) and (valL > max_val):
                        valL = max_val
                    elif (min_val!=None) and (valL < min_val):
                        valL = min_val
                    stim_valL = svalues[valL]
                    stim_name = "%s%s.wav" %(stim_base,stim_valL)
                    cond = {"class":"L","stim_name":stim_name,"type":"step","tr_num":tr_num,"val":valL,"rev":nrev}
                    yield cond # should i yield cond after deciding wether to stop iterating?
                    # check for reversal
                    valLtemp = stim_valL
                    if (valRtemp > valLtemp)==crossing: # checks if last trial's perf was consistent w/ trend
                        nrev += 1
                        crossing = not crossing

                    # decide whether to stop iterating
                    tr_num += 1
                    if tr_num < tr_min:
                        cont = True
                    elif tr_num >= tr_max:  
                        cont = False        #Margot may want to change cont = False to endblock when doing passive
                    elif nrev >= reversals:  #wait until both staircases have finished
                        cont = False 
                else: #for first left trial
                    stim_valL = svalues[valL]
                    stim_name = "%s%s.wav" %(stim_base,stim_valL)
                    cond = {"class":"L","stim_name":stim_name,"type":"step","tr_num":tr_num,"val":valL,"rev":nrev}
                    yield cond # should i yield cond after deciding wether to stop iterating?
                    lasttrialL = tr_num
                    tr_num += 1 
                    crossing = True
                    contL = True  #no longer first left trial


            else:
                self.log.info('right staircase')
                if contR:
                    last_num = lasttrialR - tr_num
                    last = self.trials[last_num]   
                    lasttrialR = tr_num
                    # staircase logic
                    if last.correct == True:
                        chg = up
                    else:
                        chg = -1 * down
                    valR += step * chg

                    # stop at max/min if we hit the rails
                    if (max_val!=None) and (valR > max_val):
                        valR = max_val
                    elif (min_val!=None) and (valR < min_val):
                        valR = min_val
                    stim_valR = svalues[valR]
                    stim_name = "%s%s.wav" %(stim_base,stim_valR)
                    cond = {"class":"R","stim_name":stim_name,"type":"step","tr_num":tr_num,"val":valR,"rev":nrev}
                    yield cond # should i yield cond after deciding wether to stop iterating?
                    # check for reversal
                    valRtemp = stim_valR
                    if (valRtemp > valLtemp)==crossing: # checks if last trial's perf was consistent w/ trend
                        nrev += 1
                        crossing = not crossing
                    # decide whether to stop iterating
                    tr_num += 1
                    if tr_num < tr_min:
                        cont = True
                    elif tr_num >= tr_max:
                        cont = False 
                    elif nrev >= reversals:   #wait until both staircases have finished
                        cont = False 

                else: #for first right trial
                    stim_valR = svalues[valR]
                    stim_name = "%s%s.wav" %(stim_base,stim_valR)
                    cond = {"class":"R","stim_name":stim_name,"type":"step","tr_num":tr_num,"val":valR,"rev":nrev}
                    yield cond # should i yield cond after deciding wether to stop iterating?
                    lasttrialR = tr_num
                    tr_num += 1
                    crossing = True
                    contR = True  #no longer first right trial

