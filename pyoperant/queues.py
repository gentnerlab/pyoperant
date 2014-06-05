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
        conditions_repeated.append(conditions)
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
    going_up = False
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

