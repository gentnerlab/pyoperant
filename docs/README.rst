pyoperant
=========

a python package for operant experiment control

Goals
-----

Framework to easily construct and share new operant behavior paradigms.

With PyOperant, you should be able to write a single behavior script that works across different species, different computers, different interfaces, different rewards, different punishments, different modalities.


What is operant conditioning?
-----------------------------

http://en.wikipedia.org/wiki/Operant_conditioning

Operant logic is easy
---------------------

- Present a stimulus

- Get the subject’s response

- If the response class matches the stimulus class, then reward the subject

- Otherwise, punish the subject

Operant code should be easy
---------------------------

::
	stimulus.play()
	response.get()
	if response.class is stimulus.class:
	    reward.give()
	else:
	    punishment.give()

But in practice...
------------------

You often have error checking, data storage, and machine-specific hardware interactions jumbled in together. If you want to share a behavioral protocol between different machines (say, from a training panel to an electrophysiology rig), you likely need to write an entirely new script. And if I can't easily share my protocol between two machines in my own lab, how can I possibly share my behavioral protocols with other scientists?

A better way
------------

Abstract hardware manipulation, isolating it from operant logic:

1. Define hardware interface(s) in a local configuration file

2. Load hardware as an object that can be manipulated

