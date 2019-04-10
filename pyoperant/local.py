import socket

hostname = socket.gethostname()

if "vogel" in hostname:
    from pyoperant.local_vogel import *
elif "zog" in hostname:
    from pyoperant.local_zog import *
elif "pi" in hostname:
    from pyoperant.local_pi import *
