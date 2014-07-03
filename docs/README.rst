pyoperant
=========

Pyoperant is a framework to easily construct and share new operant behavior paradigms.

With PyOperant, you should be able to write a single behavior script that works across different species, different computers, different hardware, different rewards, different modalities.

Operant logic is easy
---------------------

#. Present a stimulus
#. Get the subject’s response
#. If the response matches the stimulus, then reward the subject

Writing operant protocols should be easy, but in practice...
------------------

You often have error checking, data storage, and machine-specific hardware interactions jumbled in together. If you want to share a behavioral protocol between different machines (say, from a training panel to an electrophysiology rig), you likely need to write an entirely new script. And if I can't easily share my protocol between two machines in my own lab, how can I possibly share my behavioral protocols with other scientists?

A better way
------------

#. Isolate hardware manipulation from operant logic
#. Standardize operant experiment protocols for easy reuse

Documentation
-------------

http://pyoperant.readthedocs.org/en/dev/index.html


Developers
----------

Justin Kiggins & Marvin Thielk

Gentner Lab - http://gentnerlab.ucsd.edu
