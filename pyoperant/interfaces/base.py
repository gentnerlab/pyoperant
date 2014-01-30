class BaseInterface(object):
    """docstring for BaseInterface"""
    def __init__(self, arg):
        super(BaseInterface, self).__init__()
        pass

    def open(self):
        pass

    def close(self):
        pass

    def __del__(self):
        self.close()
        
