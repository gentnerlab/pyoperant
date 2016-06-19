# useful exception for going into sleep
class GoodNite(Exception):
    """ exception for when the lights should be off """
    pass

class EndExperiment(Exception):
    """ exception for when an experiment should terminate"""
    pass

class EndSession(Exception):
    """ exception for when a session should terminate """
    pass

class EndBlock(Exception):
    """ exception for when a block should terminate """
    pass

## defining Error classes for operant HW control
class Error(Exception):
    '''base class for exceptions in this module'''
    pass

class InterfaceError(Exception):
    '''raised for errors with an interface.

    this should indicate a software error, like difficulty
    connecting to an interface
    '''
    pass

class ComponentError(Exception):
    '''raised for errors with a component.

    this should indicate a hardware error in the physical world,
    like a problem with a feeder.

    this should be raised by components when doing any internal
    validation that they are working properly

    '''
    pass

class WriteCannotBeReadError(Exception):
    '''raised when an interface configured to write output cannot be read '''
    pass
