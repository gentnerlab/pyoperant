import random

def random_queue(conditions,tr_max=100):
    tr_num = 0
    while tr_num < tr_max:
        yield random.choice(conditions)
        tr_num += 1

def block_queue(conditions,shuffle=False):
    if shuffle:
        random.shuffle(conditions)
    for c in conditions:
        yield c

def staircase_queue(experiment,
                    start,
                    up=1,
                    down=3,
                    step=1,
                    min_val=None,
                    max_val=None,
                    reversals=None,
                    tr_min=0,
                    tr_max=100):
    val = start
    # first trial, don't mess with checking
    yield val
    tr_num = 1
    nrev = 0

    # subsequent trials
    cont = True
    while cont:
        
        last = experiment.trials[-1]

        # staircase logic
        if last.correct==True:
            val -= step * down
        elif last.correct==False:
            val += step * up

        # if we hit the rails
        if (max_val!=None) and (val > max_val):
            val = max_val
        elif (min_val!=None) and (val < min_val):
            val = min_val

        yield val
        tr_num += 1
        if tr_num < tr_min:
            cont = True
        elif tr_num >= tr_max:
            cont = False
        elif nrev >= reversals:
            cont = False

