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

class AdaptiveBase(object):
    """docstring for AdaptiveBase

    This is an abstract object for implementing adaptive procedures, such as
    a staircase. Importantly, any objects inheriting this need to define the
    `update()` and `next()` methods.
    """
    def __init__(self):
        super(AdaptiveBase, self).__init__()

    def __iter__(self):
        return self

    def update(self,correct):
        return NotImplemented

    def next(self):
        return NotImplemented
        

class KaernbachStaircase(AdaptiveBase):
    """ generates values for a staircase procedure from Kaernbach 1991

    This procedure returns values for each trial and assumes that larger values are
    easier. Thus, after a correct trial, the next value returned will be smaller and
    after incorrect trials, the next value returned will be larger. The magnitudes of
    these changes are stepsize_dn and stepsize_up, respectively.

    Args:
        start_val (float/int): the starting value of the procedure (default: 100)

    Kwargs:
        stepsize_up (int): number of steps to take after incorrect trial (default: 3)
        stepsize_dn (int): number of steps to take after correct trial (default: 1)
        min_val (float): minimum parameter value to allow (default: 0)
        max_val (float): maximum parameter value to allow (default: 100)
        crit (int): minimum number of trials (default: 0)
        crit_method (int): maximum number of trials (default: 100)
    Returns:
        float

    """
    def __init__(self, 
                 start_val=100,
                 stepsize_up=3,
                 stepsize_dn=1,
                 min_val=0,
                 max_val=100,
                 crit=100,
                 crit_method='trials'
                 ):
        super(KaernbachStaircase, self).__init__()
        self.val = start_val
        self.stepsize_up = stepsize_up
        self.stepsize_dn = stepsize_dn 
        self.min_val = min_val
        self.max_val = max_val
        self.crit = crit
        self.crit_method = crit_method
        self.counter = 0
        self.going_up = False

    def update(self,correct):
            
        self.val += -1*self.stepsize_dn if correct else self.stepsize_up

        if self.crit_method=='reversals':
            if correct==self.going_up: # checks if last trial's perf was consistent w/ trend
                self.counter += 1
                self.going_up = not self.going_up

        # stop at max/min if we hit the rails
        if (self.max_val!=None) and (self.val > self.max_val):
            self.val = self.max_val
        elif (self.min_val!=None) and (self.val < self.min_val):
            self.val = self.min_val

    def next(self):
        if self.counter > self.crit:
            raise StopIteration
        self.counter += 1 if self.crit_method=='trials' else 0
        return self.val
        

def staircase_queue(queue,stepper,experiment):
    """ 
    takes an 
    """
    from itertools import izip

    for conditions, staircase_val in izip(queue,stepper):
        conditions['staircase'] == staircase_val
        yield conditions
        if (experiment.do_correction==False):
            stepper.update(experiment.trials[-1].correct)

def double_staircase(experiment,condition_q):
    staircase_L = StaircaseStepper(start=100,
                                  up=1,
                                  down=3,
                                  step=1.0,
                                  min_val=0,
                                  max_val=100,
                                  tr_min=0,
                                  tr_max=1000,
                                  reversals=30,
                                  )

    staircase_R = StaircaseStepper(start=100,
                                  up=1,
                                  down=3,
                                  step=1.0,
                                  min_val=0,
                                  max_val=100,
                                  tr_min=0,
                                  tr_max=1000,
                                  reversals=30,
                                  ) #note: need to invert values

    for cond in condition_q:
        # cond has whether L or R
        if random.random.choice(['anchor','staircase'])=='staircase':
            cond['staircase']==True
            if cond['class']=='L':
                cond['value'] = staircase_L.next()
            elif cond['class']=='R':
                cond['value'] = staircase_R.next()
        else:
            cond['value'] == random.randrange(88,101)
            cond['staircase']==False

        if cond['class']=='R':
            cond['value'] = 100 - cond['value']

        yield cond

        if (experiment.do_correction==False) and (experiment.trials[-1].annotations['staircase']):
            if experiment.trial[-1]['class']=='L':
                staircase_L.update(experiment.trial[-1].correct)
            if experiment.trial[-1]['class']=='R':
                staircase_R.update(experiment.trial[-1].correct)