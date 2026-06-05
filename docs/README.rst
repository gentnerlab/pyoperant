pyoperant
=========

Pyoperant is a framework to easily construct and share new operant behavior paradigms.

With PyOperant, you can write a single behavior script that works across different species, different computers, different hardware, different rewards, different modalities.

Operant logic is easy
---------------------

#. Present a stimulus
#. Get the subject's response
#. If the response matches the stimulus, then reward the subject

Writing operant protocols should be easy, but in practice...
------------------------------------------------------------

Error checking, data storage, and machine-specific hardware interactions often obfuscate the simplicity of the task, limiting its flexibility and power. This limitation becomes increasingly apparent when deploying high-throughput behavioral experiment control systems, transferring subjects from a training panel to an electrophysiology panel, or simply trying to share behavioral protocols.

A better way
------------

PyOperant deals with these challenges by providing a cross-platform object-oriented framework to easily construct, conveniently share, and rapidly iterate on new operant behavior paradigms.

#. Abstract physical component manipulation from low-level hardware manipulation
#. Define behavioral protocols as classes which can be extended through object inheritance

Further, experimenters are able to integrate their behavioral protocols with other Python packages for online data analysis or experimental control. We currently use pyoperant in the Gentner Lab to control 36 operant panels.

Documentation
-------------

See the `pyoperant manual <https://github.com/gentnerlab/pyoperant/blob/master/pyoperant_manual.md>`_ in this repository for full documentation.

PyOperant abstracts behavioral protocol logic from hardware interactions through a machine-specific configuration file. In the local.py configuration file, the experimenter defines the operant panels available for use. A Panel consists of a collection of Component objects and a set of standard methods to manipulate the Component. These Component objects are mirrors of their physical counterparts, such as a food hopper, response port, speaker, or house light.

Behavioral protocols can be modified and extended through object inheritance. The modular architecture of PyOperant also allows experimenters to integrate their behavioral protocols with other Python packages for online data analysis or experimental control.

PyOperant's hardware support was originally written for PortAudio & Comedi. Subsequent renditions added NiDAQmx and Cambridge Electronic Designs hardware. Currently the Gentner Lab runs all PyOperant experiments on custom MagPi hardware (https://github.com/gentnerlab/rpioperant-hardware), which uses a Raspberry Pi (3B+) for GPIO, I2C-controlled PCA9685s for PWM lights and servos, and HiFiBerry for DAC.

Architecture
------------

Behaviors
~~~~~~~~~

Behaviors are Python classes which run the operant experiment. They associate the subject with the hardware panel the subject is interacting with and save experimental data appropriately. They are instantiated with various experimental parameters, such as stimulus identities and associations, block designs, and reinforcement schedules.

There are a couple of built-in behaviors: TwoAltChoice, which runs two alternative choice tasks and Lights, which simply turns the house light on and off according to a schedule. These can be inherited to change specific methods without changing the rest of the behavioral protocol.

Panels
~~~~~~

Panels are the highest level of hardware abstraction. They maintain panel components as attributes and have standard methods for resetting and testing the panel. Many Behaviors rely on specific panel components and methods to be present.

Panels are defined by the experimenter locally.

Components
~~~~~~~~~~

Components are common hardware components, such as a Hopper, a ResponsePort, a HouseLight, or an RGBLight. Many components rely on multiple hardware IO channels. For example, a Hopper requires both a solenoid (to activate the Hopper) and an IR beam detector (to check if the Hopper is raised). Calling the 'feed' method on a Hopper checks to make sure that the hopper is down, raises the hopper, checks to make sure the hopper raised, waits the appropriate length of time, then lowers the hopper, finally checking one more time to make sure the hopper dropped. If there is an incongruity between the status of the solenoid and the IR beam, the Hopper component raises the appropriate error, which the Behavior script can deal with appropriately.

Hardware IO Classes
~~~~~~~~~~~~~~~~~~~

Hardware IO classes standardize inputs and outputs that are available for Components and Panels to use.

Hardware Interfaces
~~~~~~~~~~~~~~~~~~~

Hardware interfaces are wrappers around hardware drivers and APIs that allow hardware IO classes to work.


Developers
----------

Original authors: Justin Kiggins & Marvin Thielk

Maintainer: Timothy Gentner - tgentner@ucsd.edu

Gentner Lab - http://gentnerlab.ucsd.edu
