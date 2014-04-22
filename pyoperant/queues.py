import random

class TrialQueue(object):
    """docstring for TrialQueue"""
    def __init__(self,conditions=[],tr_max=1000,tr_num=0,*args,**kwargs):
        super(TrialQueue, self).__init__()
        self.conditions = conditions

        assert tr_num < tr_max
        self.tr_max = tr_max
        self.tr_num = tr_num

    def __iter__(self):
        return self

    # Python 3 compatibility
    def __next__(self):
        return self.next()

    def next(self):
        raise NotImplementedError()

class RandomQueue(TrialQueue):
    """docstring for RandomQueue"""
    def __init__(self,*args,**kwargs):
        super(RandomQueue, self).__init__(*args,**kwargs)

    def next(self):
        if self.tr_num < self.tr_max:
            self.tr_num += 1
            return random.choice(self.conditions)
        else:
            raise StopIteration()

class BlockQueue(TrialQueue):
    """docstring for RandomQueue"""
    def __init__(self,shuffle=False,*args,**kwargs):
        super(RandomQueue, self).__init__(*args,**kwargs)
        if shuffle:
            random.shuffle(self.conditions)

    def next(self):
        if self.tr_num < self.tr_max:
            c = self.conditions[self.tr_num]
            self.tr_num += 1
            return c
        else:
            raise StopIteration()

class StaircaseQueue(TrialQueue):
    """docstring for StaircaseQueue"""
    def __init__(self,start,up=1,down=3,step=1,min_val=None,max_val=None,*args,**kwargs):
        super(StaircaseQueue, self).__init__(*args,**kwargs)
        self.start = start
        self.val = start
        self.up = up
        self.down = down
        self.step = step
        self.min_val = min_val
        self.max_val = max_val
        self.last = None

    def add_response(self,correct):
        self.last = correct

    def update(self):
        self.tr_num += 1
        if self.last==True:
            self.val -= self.step * self.down
        elif self.last==False:
            self.val += self.step * self.up
        self.last = None

        if (tr_Q.max_val<>None) and (self.val > self.max_val):
            self.val = self.max_val
        elif (tr_Q.min_val<>None) and (self.val < self.min_val):
            self.val = self.min_val

    def next(self):
        if self.tr_num < self.tr_max:
            self.update()
            return self.val
        else:
            raise StopIteration()

