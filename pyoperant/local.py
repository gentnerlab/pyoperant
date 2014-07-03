import socket

hostname = socket.gethostname()

if 'vogel' in hostname:
    from local_vogel import *
elif 'zog' in hostname:
    from local_zog import *
