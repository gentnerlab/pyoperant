import socket
import os

hostname = socket.gethostname()

if 'vogel' in hostname:
    from .local_vogel import *
elif 'zog' in hostname:
    from .local_zog import *
elif 'magpi' in hostname:
    # Magpi Rev C and Rev D board revisions have different hardware
    # (solenoid vs servo hopper). To be sure we use the correct config,
    # each client has a plain-text file at /etc/magpi_revision containing
    # either 'revc' or 'revd'. This file must be written once during initial setup:
    #
    #   echo 'revd' | sudo tee /etc/magpi_revision   # Rev D boards
    #   echo 'revc' | sudo tee /etc/magpi_revision   # Rev C boards
    #
    REVISION_FILE = '/etc/magpi_revision'
    try:
        with open(REVISION_FILE, 'r') as f:
            revision = f.read().strip().lower()
    except IOError:
        raise RuntimeError(
            "Cannot determine Magpi board revision. "
            "Expected %s containing 'revc' or 'revd'. "
            "Run: echo 'revd' | sudo tee %s" % (REVISION_FILE, REVISION_FILE)
        )

    if revision == 'revd':
        from .local_pi_revd import *
    elif revision == 'revc':
        from .local_pi_revc import *
    else:
        raise RuntimeError(
            "Unknown Magpi board revision '%s' in %s. "
            "Expected 'revc' or 'revd'." % (revision, REVISION_FILE)
        )
