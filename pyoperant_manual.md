## 1. Introduction

Welcome to the lab. This manual will guide you through everything you need to know to use PyOperant — from understanding the concepts behind operant conditioning to wiring up hardware and writing your own experiment scripts.

Do not worry if you are new to Python or to hardware. This manual is written for a range of backgrounds. Code-heavy sections include explanation, and hardware sections include diagrams and step-by-step instructions. By the end, you will be able to set up an operant panel, configure it for our system, and write a behavioral protocol from scratch.

### 1.1 What is Operant Conditioning?

Operant conditioning is a method of learning in which behavior is shaped by its consequences. A subject (a bird, rodent, or other animal) learns to perform a specific action — such as pecking a port or pressing a lever — because that action has reliably been followed by a reward (food, water) or by the avoidance of a punishment (a timeout, a light turning off).

A typical operant trial follows three steps:

  - Present a stimulus (a sound, a light, a visual pattern).

  - Wait for the subject’s response (a peck, a press, a choice).

  - Deliver a consequence based on whether the response was correct (reward) or incorrect (punishment or no reward).

By repeating this cycle thousands of times across many sessions, subjects learn to associate stimuli with correct responses. This is the foundation of nearly all behavioral experiments in the lab.

### 1.2 What is PyOperant?

PyOperant is a Python framework developed in the Gentner Lab to control operant conditioning experiments. The current version runs on Python 3; the last Python 2.7 release is tagged V2-final on GitHub. Before PyOperant, researchers had to write separate scripts for every combination of hardware, species, and experimental protocol. Sharing protocols between labs or even between rigs in the same lab was difficult.

PyOperant solves this by separating three concerns that used to be tangled together:

  - What the experiment does (the behavioral logic)

  - What hardware is being used (the panel configuration)

  - How the hardware is physically driven (the low-level interface)

This means you can write a single behavioral script that works on any rig in the lab, regardless of whether it uses different speakers, different reward mechanisms, or different computers. You can also swap out one piece of hardware without rewriting the experiment logic.

The lab currently uses PyOperant to control dozens of operant panels running simultaneously.

### 1.3 How This Manual is Organized

This manual is organized into the following chapters:

  - Chapter 2 covers the architecture of PyOperant and how its layers fit together.

  - Chapter 3 covers the MagPi client electronics: the interface board, GPIO assignments, and connectors. Chapter 4 covers the operant panel components: breakout board, hopper, peck ports, lights, audio, and wiring guide.

  - Chapter 5 covers the network and server organization: how MagPi clients and the MagPi server relate to each other.

  - Chapter 6 covers software setup: installing PyOperant and configuring your panel in local\_pi\_revd.py or local\_pi\_revc.py.

  - Chapter 7 covers system setup and usage: flashing a new client, deploying code, setting up birds, and day-to-day monitoring.

  - Chapter 8 covers existing protocols in py-behaviors and how to run them. Chapter 9 covers running experiments, monitoring sessions, and troubleshooting common problems.

  - Chapter 10 walks through writing your own behavioral experiment script step by step.

  - Chapter 11 covers analyzing behavioral data: the files PyOperant produces, and how to use the pyoperant.analysis and behav-analysis packages to load, visualize, and compute metrics from them.

## 2. PyOperant Architecture

PyOperant is organized as a stack of four layers, each one building on the layer below it. Understanding this structure will make it much easier to know where to look when something goes wrong and where to make changes when you want to modify an experiment.

### 2.1 The Four Layers

|                   |                                                                                  |
| ----------------- | -------------------------------------------------------------------------------- |
| **Layer**         | **Responsibility**                                                               |
| Behaviors         | Define the experiment logic: stimuli, responses, rewards, and session structure. |
| Panels            | Group the hardware components of a single operant box into one object.           |
| Components        | Represent individual physical parts: hoppers, peck ports, lights, speakers.      |
| Interfaces / hwio | Talk directly to the hardware: GPIO pins, PWM chips, audio drivers.              |

Each layer only talks to the layer directly below it. A Behavior tells a Panel to feed the subject; the Panel tells the Hopper component to feed; the Hopper tells the servo interface to actuate. This clean separation is what makes it possible to swap hardware without touching experiment logic.

### 2.2 Behaviors

A Behavior is a Python class that defines an entire experimental protocol. It holds information about the subject, the panel being used, the stimuli, and the reinforcement schedule. When you run an experiment, you instantiate a Behavior with a configuration file and call its run() method.

Internally, run() drives a state machine. At the top level, the experiment loops continuously through three states: idle (waiting for the session schedule to be active), sleep (lights off, waiting for daytime), and session (running trials). Within each session, the state machine cycles through session\_pre (setup), session\_main (the trial loop), and session\_post (cleanup and data saving). Each state is a method that returns the name of the next state.

PyOperant ships with two built-in behaviors:

  - TwoAltChoiceExp: runs a two-alternative forced-choice task. The subject hears a stimulus and must peck the left or right port to indicate its choice. Correct responses are rewarded; incorrect responses result in a timeout.

  - Lights: a simple behavior that turns the house light on and off according to a daily schedule. Useful for housing birds on a light cycle without running a full experiment.

You can inherit from either of these to create your own experiment. For example, if you want to run a two-alternative choice task but change how stimuli are selected, you would subclass TwoAltChoiceExp and override only the stimulus selection method. For experiments with a fundamentally different structure (go/no-go, free operant, autoshaping), inherit from BaseExp directly.

### 2.3 Panels

A Panel is a Python object that represents one operant box. It holds references to all the components in that box as attributes. For example, a typical panel might have:

  - panel.center — the center peck port

  - panel.left — the left peck port

  - panel.right — the right peck port

  - panel.hopper — the food hopper

  - panel.house\_light — the house light

  - panel.speaker — the audio output

Panels are defined locally on each MagPi client. The file pyoperant/local.py acts as a router: it reads the machine’s hostname and imports the matching local config file. For zog and vogel machines this is done by hostname alone. For MagPi clients, local.py reads a board revision file at /etc/magpi\_revision to determine whether to load the Rev C (solenoid hopper) or Rev D (servo hopper) configuration. This means you configure hardware once per machine, and the rest of the code picks it up automatically.

Every Panel must implement a reset() method that puts all components into a known safe state, and a test() method that exercises each component to verify it is working. Behaviors call reset() at the start and end of sessions.

### 2.4 Components

Components are Python objects that represent individual physical parts of an operant panel. Each component class knows about the hardware it controls and exposes a clean, hardware-agnostic interface to the rest of the code.

For example, the Hopper component exposes feed(dur) — the calling code does not need to know whether the hopper is driven by a solenoid or a servo, or which GPIO pin controls it. All of that is handled inside the component.

The components currently available in PyOperant include:

|                    |                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Component**      | **Description**                                                                                              |
| Hopper             | Controls the food hopper. Raises and lowers to deliver food reward. Monitors an IR beam to confirm position. |
| PeckPort           | A response port with an IR beam (detects pecks) and an LED (cue light).                                      |
| HouseLight         | The main chamber light. Can be turned on, off, or used for timeout punishments.                              |
| RGBLight           | A three-color cue light with independent red, green, and blue channels.                                      |
| LEDStripHouseLight | A four-channel RGBW PWM house light for color-controlled illumination.                                       |

### 2.5 Hardware IO (hwio) and Interfaces

The bottom two layers of the stack handle the actual communication with hardware. They are separated to keep the component code clean.

hwio classes (BooleanInput, BooleanOutput, PWMOutput, AudioOutput) represent a single channel of input or output. They do not know what hardware they are connected to — they only know how to call the interface below them.

Interface classes (such as RaspberryPiInterface) are wrappers around specific hardware drivers. The RaspberryPiInterface uses pigpio to talk to GPIO pins and PCA9685 PWM chips over I2C. If the lab ever switches to different hardware, only the interface class needs to change.

The connection between an hwio object and a channel on the hardware is made through a params dictionary. For example, a BooleanInput connected to GPIO pin 17 would be created with params={'channel': 17}.

## 3. MagPi Client Electronics

This chapter covers the MagPi client electronics: the RPiOperant interface board, Raspberry Pi GPIO assignments, back and front panel connectors, PCA9685 address reference, and load cell interface. For operant panel components see Chapter 4.

The hardware described here is Mainboard Rev D (March 2026). Earlier revisions used a solenoid-driven hopper and a linear power supply; Rev D replaces both with a servo-driven hopper and a switching power supply. Where behavior differs from earlier revisions, this is noted.

### 3.1 System Overview

The RPiOperant system for each box consists of four physical assemblies that work together:

  - The MagPi client — a custom electronics box containing the Raspberry Pi, HiFiBerry audio amplifier, and the RPiOperant interface board. This is the brain of the system.

  - The operant panel — the sheet metal panel inside the sound isolation chamber that holds the peck ports, hopper, and cue lights.

  - The breakout board — a small PCB mounted inside the chamber that connects the 50-pin IDC cable from the MagPi client to the individual panel components via Molex connectors.

  - The sound isolation chamber — an acoustically isolated box that houses the operant panel, speaker, and camera.

The MagPi client connects to the panel via a 50-pin IDC ribbon cable that runs from the back panel connector directly to the breakout board inside the chamber. Audio is output by the HiFiBerry Amp2, which connects to a speaker inside the chamber via an audio cable on the back panel.

A MagPi server — a Ubuntu desktop computer — manages the local network, distributes code updates via git, and aggregates behavioral data from all boxes via rsync. Each MagPi client is assigned a static IP address of 192.168.1.XX, where XX is the box number.

### 3.2 The RPiOperant Interface Board

The interface board is a custom PCB designed in the Gentner Lab (SCH-000001, Rev D). It sits inside the MagPi client enclosure and plugs onto the Raspberry Pi’s 40-pin GPIO header. The HiFiBerry Amp2 audio board plugs on top of the Raspberry Pi through a separate connector on the interface board.

The board provides the following subsystems:

#### Power Supply

The Rev D board uses a TPSM64404RCHR synchronous step-down module as its main power supply. It accepts a wide input voltage range (14–24VDC) and generates three regulated output rails:

  - \+12V @ 2A — powers the RGBW house lights via MOSFET drivers.

  - \+6V @ 2A — powers the food hopper servo motor.

  - \+3.3V (from a TPS7A2633 LDO) — powers the IR beam circuits, PWM controllers, and GPIO logic.

A power-good (PG) circuit monitors both the 3.3V and 5V rails using APX803L40 supervisors. The front panel green LED illuminates only when all rails are healthy. If the green LED does not light on power-up, do not proceed — check the input supply and connections.

> *ALWAYS disconnect power to the MagPi client before working on it or any connected peripherals. The power supply is sensitive to short circuits. Never connect or disconnect the 50-pin IDC cable while powered.*
> *Rev D replaced the earlier linear regulator design (7812 + 7833 + TIP42 transistors) with the switching regulator. The +24V rail and the red front panel LED from earlier revisions are deprecated and not present on Rev D boards.*

#### IR Beam Interface

Each IR beam sensor (peck port and hopper) connects to one channel of the IR beam interface. The interface uses two SN74LVC14AQDRQ1 hex Schmitt-trigger inverter ICs. Each channel has a 4.32 kΩ pull-up resistor to 3.3V on the input.

How it works: the IR LED transmits a constant beam to an IR phototransistor. When the beam is clear, the transistor conducts, pulling the Schmitt trigger input low, and the output goes high. When the beam is broken (a peck), the transistor stops conducting, the input is pulled high by the 4.32 kΩ resistor, and the output goes low. This inverted, noise-cleaned signal is passed to a GPIO pin on the Raspberry Pi.

Because the output is inverted, broken beam = low GPIO = logical 0. In software this is corrected by setting inverted=True on the relevant PeckPort or Hopper component (see Section 6.3).

The interface board supports 12 IR channels total: hopper, left, center, right, and 8 auxiliary channels (AUX\_IR\_1 through AUX\_IR\_8).

#### PWM LED Controller (Lights)

A PCA9685 16-channel PWM controller (U1) handles all LED outputs. It communicates with the Raspberry Pi over I2C and generates PWM waveforms independently, so the RPi only needs to set duty cycles rather than bit-bang the signals. The chip runs at 1000 Hz for LED control.

The I2C address of U1 is 0x55. This is a hardcoded address determined by which address pins (A0–A5) are pulled high on the board. The 16 channels are assigned as follows:

|                 |               |                                              |
| --------------- | ------------- | -------------------------------------------- |
| **PWM Channel** | **Signal**    | **Notes**                                    |
| 0               | HOUSELIGHT\_R | Red house light channel (via MOSFET, 12V)    |
| 1               | HOUSELIGHT\_G | Green house light channel (via MOSFET, 12V)  |
| 2               | HOUSELIGHT\_B | Blue house light channel (via MOSFET, 12V)   |
| 3               | HOUSELIGHT\_W | White house light channel (via MOSFET, 12V)  |
| 4               | LFT\_LED      | Left peck port cue LED (3.3V, 330Ω series)   |
| 5               | CTR\_LED      | Center peck port cue LED (3.3V, 330Ω series) |
| 6               | RGT\_LED      | Right peck port cue LED (3.3V, 330Ω series)  |
| 7               | AUX\_LED\_1   | Auxiliary LED 1                              |
| 8               | AUX\_LED\_2   | Auxiliary LED 2                              |
| 9               | AUX\_LED\_3   | Auxiliary LED 3                              |
| 10              | AUX\_LED\_4   | Auxiliary LED 4                              |
| 11–12           | NC            | Not connected                                |
| 13              | RGB\_CUE\_R   | RGB cue light — red channel                  |
| 14              | RGB\_CUE\_G   | RGB cue light — green channel                |
| 15              | RGB\_CUE\_B   | RGB cue light — blue channel                 |

The house light channels (0–3) do not drive the LEDs directly. Instead the PWM signal switches an SQ2364EES N-channel MOSFET, which in turn switches the 12V supply to the high-power RGBW LED panel. This is necessary because the LED panel requires up to 330 mA per channel, far more than the PCA9685 can source.

#### PWM Servo Controller (Hopper)

A second PCA9685 (U7) is dedicated to servo control. It runs at 50 Hz — the standard frequency for hobby servos. This chip is connected to the same I2C bus as U1 but at a different address (0x45, set by pulling address pins A0 and A2 high).

The servo channels available on the board are:

|                 |               |                             |
| --------------- | ------------- | --------------------------- |
| **PWM Channel** | **Signal**    | **Notes**                   |
| 0               | HOPPER\_CTL   | Food hopper servo (primary) |
| 1               | AUX\_SERVO\_1 | Auxiliary servo 1           |
| 2               | AUX\_SERVO\_2 | Auxiliary servo 2           |
| 3               | AUX\_SERVO\_3 | Auxiliary servo 3           |
| 4               | AUX\_SERVO\_4 | Auxiliary servo 4           |
| 5–15            | NC            | Not connected               |

The servo is powered from the +6V rail. Standard hobby servos typically accept 4.8–6V, so this is within spec for most servos. The servo signal line is driven at 3.3V logic from the PCA9685 — this is compatible with most servo controllers.

> *In pyoperant/interfaces/raspi\_gpio\_.py, the servo chip is identified by passing servo=True in the params dictionary when creating a PWMOutput for the hopper. This routes the write call to the second PCA9685 instance rather than the lights chip.*

#### House Light MOSFET Drivers

Four SQ2364EES N-channel MOSFETs (Q3–Q6) switch the 12V supply to the four house light channels. Each MOSFET gate is driven by a PWM channel from U1. The MOSFETs do not require heatsinks at normal house light current levels.

#### Audio

A HiFiBerry Amp2 audio amplifier board sits on top of the Raspberry Pi and connects through a 2x20 pin header on the interface board. It provides two amplified audio output channels for the speaker inside the chamber. Audio is connected via a 4-pin Molex connector on the back of the enclosure (Yellow/Blue/Blue/Yellow, left channel closest to the power connector).

The HiFiBerry also regulates the 5V supply for the Raspberry Pi from the +12V rail, so the RPi does not need a separate USB power supply.

> *The audio interface also includes two trim potentiometers and an RC high-pass filter to produce line-level audio outputs for OpenEphys analog recording. See Section 3.5 for OpenEphys connections.*

#### Load Cell

A SparkFun HX711 load cell amplifier (M3) is mounted on the interface board. It connects to a load cell sensor inside the operant box that measures the weight of a bird on the perch. Data and clock signals go to GPIO17 and GPIO8 on the Raspberry Pi respectively. Jumpers JP1 allow the load cell amplifier to be disconnected from the RPi to free up those GPIO pins if load cell functionality is not needed.

### 3.3 Raspberry Pi GPIO Assignments

The following table shows the full pin assignment for the Raspberry Pi 3B+ as used on the RPiOperant board. BCM (Broadcom) pin numbers are used throughout the codebase.

|             |              |                |               |                                                  |
| ----------- | ------------ | -------------- | ------------- | ------------------------------------------------ |
| **RPi Pin** | **BCM GPIO** | **Signal**     | **Direction** | **Notes**                                        |
| 3           | GPIO2 (SDA)  | SDA            | Bidirectional | I2C data — shared by both PCA9685 chips          |
| 5           | GPIO3 (SCL)  | SCL            | Bidirectional | I2C clock — shared by both PCA9685 chips         |
| 7           | GPIO4        | HiFiBerry Mute | Output        | HiFiBerry soft mute control                      |
| 8           | GPIO14 (TXD) | TXD            | Output        | Serial transmit                                  |
| 10          | GPIO15 (RXD) | RXD            | Input         | Serial receive                                   |
| 11          | GPIO17       | Load Cell DAT  | Input         | HX711 data line                                  |
| 13          | GPIO27       | GPIO27         | I/O           | Auxiliary GPIO                                   |
| 15          | GPIO22       | GPIO22         | I/O           | Auxiliary GPIO                                   |
| 16          | GPIO23       | AUX IR 1       | Input         | Auxiliary IR beam 1                              |
| 18          | GPIO24       | AUX IR 2       | Input         | Auxiliary IR beam 2                              |
| 19          | GPIO10       | AUX IR 6       | Input         | Auxiliary IR beam 6                              |
| 21          | GPIO9        | AUX IR 4       | Input         | Auxiliary IR beam 4                              |
| 22          | GPIO25       | AUX IR 3       | Input         | Auxiliary IR beam 3                              |
| 23          | GPIO11       | AUX IR 5       | Input         | Auxiliary IR beam 5                              |
| 24          | GPIO8        | Load Cell CLK  | Output        | HX711 clock line                                 |
| 26          | GPIO7        | AUX IR 7       | Input         | Auxiliary IR beam 7                              |
| 29          | GPIO5        | Hopper IR      | Input         | Hopper position IR beam                          |
| 31          | GPIO6        | Left IR        | Input         | Left peck port IR beam                           |
| 32          | GPIO12       | AUX IR 8       | Input         | Auxiliary IR beam 8                              |
| 33          | GPIO13       | Center IR      | Input         | Center peck port IR beam                         |
| 36          | GPIO16       | Hopper CTL     | Output        | Not directly used — servo driven via PCA9685 I2C |
| 37          | GPIO26       | Right IR       | Input         | Right peck port IR beam                          |

> *GPIO16 appears in the old codebase as HOPPER\_TRIG\_GPIO for the solenoid. In the Rev D servo design, the servo is driven by the second PCA9685 over I2C — GPIO16 is not used by PyOperant for the hopper in normal operation.*

### 3.4 Back Panel Connectors

The back panel of the MagPi client enclosure (Rev D) has three connections:

  - 14–24V DC power input (center-positive barrel connector)

  - 2-channel audio output (4-pin Molex: Yellow/Blue/Blue/Yellow, left channel closest to the power connector)

  - One 50-pin IDC connector — carries all panel signals

The 50-pin IDC connector on the back panel mates with a 50-pin IDC ribbon cable that runs directly to the breakout board inside the sound isolation chamber. Unlike earlier MagPi revisions which used two DB-25 connectors, Rev D uses a single 50-pin connector for all signals.

> *Earlier MagPi revisions (pre-Rev D) used two DB-25 connectors (upper and lower) on the back panel. Do not use pre-Rev D cables with a Rev D board.*

#### 50-Pin IDC Connector Pinout

Pin 1 is marked with a red stripe on the IDC ribbon cable. The connector is keyed — always align the key before seating.

|         |                   |                                          |
| ------- | ----------------- | ---------------------------------------- |
| **Pin** | **Signal**        | **Notes**                                |
| 1       | \+12V             | House light supply                       |
| 2       | \+12V             | House light supply                       |
| 3       | \+6V              | Servo supply                             |
| 4       | \+6V              | Servo supply                             |
| 5       | \+3.3V            | Logic supply                             |
| 6       | \+3.3V            | Logic supply                             |
| 7       | GND               |                                          |
| 8       | GND               |                                          |
| 9       | RGB\_CUE\_G       | RGB cue light — green                    |
| 10      | RGB\_CUE\_B       | RGB cue light — blue                     |
| 11      | RGB\_CUE\_R       | RGB cue light — red                      |
| 12      | HOPPER\_CTL       | Hopper servo PWM signal (PCA9685 U7 ch0) |
| 13      | RGT\_LED          | Right peck port cue LED                  |
| 14      | CTR\_LED          | Center peck port cue LED                 |
| 15      | LFT\_LED          | Left peck port cue LED                   |
| 16      | RGT\_IR\_SENSE    | Right peck port IR beam                  |
| 17      | CTR\_IR\_SENSE    | Center peck port IR beam                 |
| 18      | LFT\_IR\_SENSE    | Left peck port IR beam                   |
| 19      | HOPPER\_IR\_SENSE | Hopper position IR beam                  |
| 20      | LOADCELL\_A−      | Load cell sense −                        |
| 21      | LOADCELL\_A+      | Load cell sense +                        |
| 22      | LOADCELL\_E−      | Load cell excitation −                   |
| 23      | LOADCELL\_E+      | Load cell excitation +                   |
| 24      | HOUSELIGHT\_B     | House light — blue                       |
| 25      | HOUSELIGHT\_W     | House light — white                      |
| 26      | HOUSELIGHT\_R     | House light — red                        |
| 27      | HOUSELIGHT\_G     | House light — green                      |
| 28      | GPIO\_16          | Auxiliary GPIO                           |
| 29      | TXD               | RPi serial transmit                      |
| 30      | GND               |                                          |
| 31      | RXD               | RPi serial receive                       |
| 32      | AUX\_LED\_1       | Auxiliary LED 1                          |
| 33      | AUX\_LED\_2       | Auxiliary LED 2                          |
| 34      | AUX\_LED\_3       | Auxiliary LED 3                          |
| 35      | AUX\_LED\_4       | Auxiliary LED 4                          |
| 36      | AUX\_SERVO\_1     | Auxiliary servo 1 (PCA9685 U7 ch1)       |
| 37      | AUX\_SERVO\_2     | Auxiliary servo 2 (PCA9685 U7 ch2)       |
| 38      | AUX\_SERVO\_3     | Auxiliary servo 3 (PCA9685 U7 ch3)       |
| 39      | AUX\_SERVO\_4     | Auxiliary servo 4 (PCA9685 U7 ch4)       |
| 40      | USB1\_VBUS        | USB1 power                               |
| 41      | USB1\_D−          | USB1 data −                              |
| 42      | USB1\_D+          | USB1 data +                              |
| 43      | AUX\_IR\_1        | Auxiliary IR beam 1                      |
| 44      | AUX\_IR\_2        | Auxiliary IR beam 2                      |
| 45      | AUX\_IR\_3        | Auxiliary IR beam 3                      |
| 46      | AUX\_IR\_4        | Auxiliary IR beam 4                      |
| 47      | AUX\_IR\_5        | Auxiliary IR beam 5                      |
| 48      | AUX\_IR\_6        | Auxiliary IR beam 6                      |
| 49      | AUX\_IR\_7        | Auxiliary IR beam 7                      |
| 50      | AUX\_IR\_8        | Auxiliary IR beam 8                      |

### 3.5 Front Panel Connectors

The front panel provides diagnostic and electrophysiology interface connections:

  - Two USB-A ports (USB1 and USB2) — pass-through to the panel via the 50-pin IDC connector, allowing USB peripherals inside the chamber to be accessed from outside.

  - Front panel DB-9 — bidirectional access to the main operant signals (Left, Center, Right peck ports and Hopper trigger). A handheld switch or test jig can plug in here to simulate pecks or read signal states. Also carries serial RXD/TXD and 3.3V power.

  - OpenEphys Analog (HDMI connector) — carries line-level left and right audio channels from the HiFiBerry, plus serial TXD, to the OpenEphys ADC for synchronization with neural recordings.

  - OpenEphys Digital (HDMI connector) — carries 5V-logic versions of the main operant signals (left peck, center peck, right peck, hopper trigger) plus three auxiliary GPIOs. A SN74LVC4245A level shifter converts the 3.3V RPi signals to 5V for OpenEphys.

The front panel also has a power-good green LED (illuminates when all supply rails are healthy) and a spare DE-9 auxiliary connector.

### 3.6 PCA9685 Address Pin Reference

The I2C address of a PCA9685 chip is 0x40 plus the value of address pins A0–A5. Each pin adds the following when pulled high:

|         |                              |
| ------- | ---------------------------- |
| **Pin** | **Value added to base 0x40** |
| A0      | 0x01                         |
| A1      | 0x02                         |
| A2      | 0x04                         |
| A3      | 0x08                         |
| A4      | 0x10                         |
| A5      | 0x20                         |

The lights chip (U1) on the RPiOperant board is configured for address 0x55 (0x40 + 0x15, i.e. A0, A2, A4 pulled high). The servo chip (U7) is configured for address 0x45 (0x40 + 0x01 + 0x04, i.e. A0 and A2 pulled high). Always verify addresses with i2cdetect -y 1 after assembly.

### 3.7 Load Cell

The RPiOperant Rev D board includes an HX711 24-bit load cell amplifier (M3) that connects to a strain gauge load cell mounted inside the operant box. The intended application is continuous weighing of food in the hopper, allowing the experiment to track consumption per trial or per session. Data and clock signals connect to GPIO17 and GPIO8 on the Raspberry Pi respectively. If load cell functionality is not needed, jumper JP1 disconnects the HX711 from the RPi to free those GPIO pins for other use. See Appendix B.7 for full HX711 electrical specifications.

*TODO: This section needs expansion to cover physical load cell installation and mounting, wiring to the HX711 on the breakout board, software driver integration (GPIO bit-banging protocol), calibration procedure (tare and known-weight span calibration), and recommended Python libraries. A companion section on using load cell data during experiments (logging consumption, triggering events on weight threshold) will be added in Section 6 when the load cell workflow is finalized.*

## 4. Operant Panel Components

### 4.1 The Breakout Board

Inside each sound isolation chamber, a small breakout board sits between the 50-pin IDC cable from the MagPi client and the individual panel components. It provides clearly labeled Molex connector positions for:

  - Hopper (+24V solenoid power and signal for Rev C, or +6V servo power and signal on Rev D)

  - Left, Center, and Right peck ports (IR beam sense and cue LED, each with separate Molex)

  - House lights (RGBW, one Molex with +12V, White, Red, Green, Blue)

  - RGB cue light (R, G, B, GND)

  - Load cell (A+, A−, E+, E−)

The breakout board accepts the female 50-pin IDC end of the ribbon cable and routes the most common signals to labeled Molex connectors. Any lines not routed to a Molex connector can be accessed via the screw terminals.

> *There is no dedicated ground wire on the 50-pin IDC connector beyond pins 7, 8, and 30. Ground is also provided through the shield of the IDC cable, which connects to the enclosure chassis ground. Always use a shielded cable, or add a separate ground wire between the MagPi client chassis and the breakout board. Any signals not broken out to Molex connectors are accessible via screw terminals on the breakout board.*

### 4.2 The Food Hopper

The food hopper is a small tray that holds bird food. When the subject earns a reward, a servo motor raises the tray into the feed position so the subject can eat. After the reward duration, the servo lowers the tray.

**The IR position sensor is mounted so that its beam is broken when the hopper tray is in the raised (feed) position. This allows PyOperant to confirm the hopper position after commanding it to move, and potentially raise an error accordingly.**

#### Wiring the Hopper Servo

The servo connects to the breakout board’s HOPPER connector. The servo has three wires:

  - Red — power (+6V from the MagPi client via 50-pin IDC pin 3 or 4)

  - White — PWM control signal (from PCA9685 U7, channel 0)

  - Black — ground

> *Verify the servo connector polarity before applying power. Reversed power will damage the servo. Check the servo datasheet for wire color conventions, as these vary by manufacturer.*

The hopper IR sensor connects to the breakout board’s HOPPER IR connector with a 3-pin Molex: +3.3V, IR signal (to Hopper IR GPIO, BCM pin 5), and GND.

#### Tuning Servo Angles

The exact angle values needed to raise and lower the hopper vary between panels due to differences in servo mounting and mechanical tolerances. These values must be tuned empirically for each panel and recorded in local\_pi\_revd.py as up\_angle and down\_angle. See Section 6.4 for the tuning procedure.

### 4.3 Peck Ports

Each peck port is a 3D-printed body that holds an IR break-beam sensor and a cue LED. It is mounted to the sheet metal panel with \#4-40 1/2" flat head screws and nylon lock washers. A machined plastic pecking piece covers the port opening.

#### IR Beam

Each peck port contains an IR emitter/detector pair. The emitter and detector mount in opposite sides of the port body such that the bird’s beak breaks the beam when it pecks into the port. The IR sensor connects to the breakout board’s corresponding peck port connector (3-pin Molex: +3.3V, signal, GND).

BCM pin assignments for peck port IR beams:

|                  |              |                    |
| ---------------- | ------------ | ------------------ |
| **Port**         | **BCM GPIO** | **50-pin IDC Pin** |
| Hopper IR        | GPIO5        | 19                 |
| Left peck port   | GPIO6        | 18                 |
| Center peck port | GPIO13       | 17                 |
| Right peck port  | GPIO26       | 16                 |

#### Cue LED

Each peck port LED connects to the breakout board’s corresponding LED connector (2-pin Molex: signal, GND). The LED is driven directly by the PCA9685 PWM output through a 330 Ω series resistor. PWM channel assignments are listed in Section 3.2.

In software, peck port LEDs are configured as PWMOutput objects, allowing brightness control. The PeckPort component in PyOperant has separate on() and off() methods that write 100% and 0% duty cycle respectively.

### 4.4 House Lights

Each sound isolation chamber has four high-output LED panels mounted to the ceiling: red, green, blue, and white (RGBW). They are mounted with glued-on magnets and each connects to the breakout board’s HOUSE LIGHTS connector via a Molex connector.

The house lights run at 12V and draw up to 330 mA per channel. They are controlled by the four MOSFET driver circuits on the interface board (PWM channels 0–3). Brightness is set by the PWM duty cycle, allowing fine control over light level and spectrum.

In software, the house lights are instantiated as a LEDStripHouseLight component, which takes a list of four PWMOutput objects and provides on(), off(), timeout(), and change\_color() methods.

> *With all four channels at full brightness, the house lights are the largest current draw on the 12V rail. The +12V supply is rated at 2A continuous. Running all four channels simultaneously at 100% approaches this limit. In practice, the white channel alone is sufficient for normal behavioral sessions.*

### 4.5 Speaker and Audio

A speaker inside each sound isolation chamber connects to the back panel of the MagPi client via an audio cable (two channels, one for stimulus playback and one optionally for synchronization signals). The HiFiBerry Amp2 drives the speaker directly.

In PyOperant, audio is managed through the PyAudioInterface and an AudioOutput hwio object. Stimulus wav files are queued and played via panel.speaker.queue() and panel.speaker.play(). The lab’s Zog panels require 48 kHz wav files; check your local config’s audio interface class for any sample rate requirements.

### 4.6 Step-by-Step Panel Wiring Guide

This section walks through connecting all components for a new or reconfigured panel. Before starting, confirm you have:

  - A fully assembled and tested MagPi client (board powered, green LED illuminated, RPi accessible over SSH)

  - A sound isolation chamber with ceiling house lights already installed

  - A sheet metal panel with hopper, three peck ports, and cue light(s) mounted

  - A breakout board mounted inside the chamber

  - 50-pin IDC ribbon cable and audio cable

> *Power off the MagPi client before making any connections. Never connect or disconnect the 50-pin IDC cable or Molex connectors while powered.*

#### Step 1: Connect the MagPi Client to the Chamber

1.  Run the 50-pin IDC ribbon cable from the MagPi client back panel to the breakout board inside the chamber. Align pin 1 (red stripe on ribbon) with the key on both connectors before seating.

2.  Run the audio cable from the MagPi client back panel audio connector to the speaker inside the chamber.

#### Step 2: Connect House Lights

3.  Connect each house light’s Molex connector to the corresponding position on the breakout board (labeled +12V, White, Red, Green, Blue).

4.  Verify polarity — the +12V wire must connect to the +12V terminal, not to a signal or GND pin.

#### Step 3: Connect Peck Ports

5.  For each peck port (Left, Center, Right):

6.  Connect the IR sensor Molex to the port’s IR connector on the breakout board (+3.3V, signal, GND). Verify the signal wire matches the correct GPIO (see Section 4.3).

7.  Connect the cue LED Molex to the port’s LED connector on the breakout board (signal, GND).

#### Step 4: Connect the Hopper

8.  Connect the hopper IR sensor Molex to the HOPPER IR connector on the breakout board (+3.3V, signal, GND).

9.  Connect the servo connector to the HOPPER servo connector on the breakout board. Verify the wire order matches the servo’s datasheet (typically: GND, +6V, signal).

> *The servo signal is carried on 50-pin IDC pin 12 (HOPPER\_CTL) from the MagPi client. +6V is supplied on pins 3/4’s power supply.*

#### Step 5: Power On and Verify

10. Apply power to the MagPi client. The green power-good LED should illuminate within a few seconds of power-up.

11. SSH into the MagPi client: ssh bird@192.168.1.XX

12. Confirm pigpiod is running: sudo pigpiod

13. Run i2cdetect -y 1 and confirm two devices are visible: 0x55 (lights PCA9685) and 0x45 (servo PCA9685).

14. Run python3 scripts/test\_panel.py (it auto-detects the board revision from /etc/magpi\_revision) and watch each component cycle. Fix any failures before placing a bird in the panel.

## 5. Network and Server Organization

Each MagPi client runs as an autonomous unit — PyOperant controls the experiment, manages the light schedule, and saves data locally without needing a continuous connection to any server. The MagPi server provides centralized code distribution, data aggregation, process orchestration, time synchronization, mail relay, and remote monitoring across all clients/boxes in the lab.

### 5.1 Network Topology

The RPiOperant network is a private LAN hosted on the MagPi server. The server has two wired Ethernet interfaces:

  - eno1 — connected to the UCSD campus network (IP 132.239.182.189). This is the WAN-facing interface managed by SSCF. 

  - eno2 — connected to a 48-port Ethernet switch to which all MagPi clients connect (IP 192.168.1.100, netmask 255.255.255.0).

Each MagPi client is assigned a static IP address of 192.168.1.XX, where XX is the box number (e.g., box 3 has IP 192.168.1.3). This is normally configured when each client is intially setup (see section6) and can be changed in /etc/network/interfaces on each client:

```
auto eth0
iface eth0 inet static
address 192.168.1.XX
netmask 255.255.255.0
gateway 192.168.1.100
```

Note: the `gateway` line is set for historical reasons but is not functional — `ip_forward` is disabled on the server and there are no NAT/MASQUERADE rules, so MagPi clients have no routed internet access. This is intentional, not a bug: it keeps the client subnet isolated. Anything a client needs from the outside world (code, time sync, mail relay) goes through a specific server-side service instead of general routing — see 5.2 below.

The server hostname is magpi (magpi.ucsd.edu) 

The hostname of each client is set to magpiXX (e.g., magpi03, see section 6). To log in to a client from the MagPi server or any machine on the LAN:

```
ssh bird@192.168.1.XX, or
ssh magpixx
```

Video cameras are on a separate subnet (192.168.2.0/24) managed through PoE switches. Each camera's IP is 192.168.2.1XX where XX is the box number.

### 5.2 The MagPi Server

The MagPi server is a rackmount computer (Supermicro, Ubuntu 24.04, as of July 2026) provisioned under UCSD's SSCF and managed centrally by CFEngine. Most of the server's base configuration (Postfix, the firewall, NTP's inbound access) is not something the lab can edit directly — changes to those pieces have to go through SSCF, and any live edits not backed by a matching CFEngine policy change tends to get silently reverted.

The Magpi server performs six functions for the RPiOperant system:

| Function | Purpose | Runs | Code |
|---|---|---|---|
| Git Code Distribution | Lets clients pull code without direct GitHub access | On demand (`git pull`) | N/A — plain git remotes |
| NTP Time Synchronization | Keeps client clocks correct (light schedule, timestamps depend on this) | Continuous (ntpsec daemon) | Server: `ntpsec`. Client: `systemd-timesyncd` |
| Data Aggregation | Pulls each active subject's data to the server, writes a combined status file | Every 15 min (cron) | `glab-common-py`: `glab_common/allsummary.py` |
| Process Orchestration | Reconciles what's running on each box against what should be running | Every 5 min (cron) | `rpioperantctl`: `rpioperantctl.py` |
| Mail Relay | Lets clients (with no direct internet) relay error-notification email out through the server | Continuous (Postfix) | Server: Postfix. Client: `pyoperant`'s `SMTPHandler` |
| Dashboard | Renders per-bird plots and a login-gated status page from the aggregated data | Every 15 min (cron) | `websitebehavior`: `daily_website.sh` → `website_update_cron.py` |

Each is detailed below, in the same order.

#### Git Code Distribution

The MagPi server is the git remote for all MagPi clients. The clients cannot reach GitHub directly; instead, repositories are first cloned from GitHub onto the server, and the clients then clone from the server.

To set up a repository on the server:

```
git clone git@github.com:gentnerlab/pyoperant.git ~/code/pyoperant
```

(Use the SSH remote form, `git@github.com:...`, not `https://...` — an HTTPS remote will just fail every push/pull with a credential prompt. All three server-side pipeline repos — `pyoperant`, `glab-common-py`, `rpioperantctl` — should be on SSH remotes; if `git remote -v` shows `https://github.com/...` for any of them, switch it with `git remote set-url origin git@github.com:gentnerlab/<repo>.git`.)

To clone from the server onto a client (run on the client):

```
git clone bird@192.168.1.100:~/code/pyoperant ~/pyoperant
```

To update a client after pushing changes to the server:

```
cd ~/pyoperant && git pull origin master
```

The same workflow applies to py-behaviors (the lab's private behavior repository) and any other code the clients need.

#### NTP Time Synchronization

The MagPi clients have no on-board real-time clock. They synchronize their clocks from the MagPi server on boot and periodically during operation. This is critical: the light schedule (sunrise/sunset calculations) and all behavioral timestamps depend on the clock being correct.

Time synchronization is configured in /etc/systemd/timesyncd.conf on each client:

```
NTP=time.ucsd.edu 192.168.1.100
```

Note: the `time.ucsd.edu` entry here is effectively dead weight — clients have no routed internet access (see 5.1), so only the `192.168.1.100` half actually resolves. Harmless, just not doing anything.

On the server, NTP is provided by `ntpsec` (`/etc/ntpsec/ntp.conf`), synced upstream to `time.ucsd.edu`/`bigben.ucsd.edu`. The config includes a `restrict` line explicitly permitting query access from the whole MagPi subnet:

```
restrict 192.168.0.0 mask 255.255.0.0 nomodify notrap
```

If clients ever show incorrect times after reboot, check `sudo systemctl status ntpsec` on the server first, then confirm the `restrict` line above is still present (it's CFEngine-managed like everything else on this box, so if it's disappeared, that's a CFEngine policy question for SSCF, not something to hand-edit back in permanently).

To manually check that time is synchronized on a client:

```
date
timedatectl status
```

#### Data Aggregation (`allsummary.py`)

Runs every 15 minutes via cron on the server:

```
*/15 * * * * /home/bird/anaconda3/bin/python3 /home/bird/code/glab-common-py/glab_common/allsummary.py > /home/bird/allsummary.log 2>&1
```

For every box marked enabled in `panel_subject_behavior` (5.3), it rsyncs that subject's own data folder from the client, then parses `.summaryDAT` and today's trial CSVs into one combined status file.

**What it pulls.** Long rsyncs can cause problems, so the rsync source is scoped to just the active subject's own folder — `bird@<box>:/home/bird/opdat/B<bird>/`, not the box's whole `opdat/` tree. A box accumulates a folder for every subject that's ever run there (previous residents of that chamber), and no client ever runs more than one bird at a time, so pulling the whole tree just re-transfers old, orphaned data on every cycle. Stimulus libraries used in specific experiments are not generally backed up. To avoid copying large stimulus libraries three "excludes" apply to each box's rsync:

| Exclude | Always applied? | Purpose |
|---|---|---|
| `Generated_Songs` | Yes | Per-session regenerated stimulus output, never irreplaceable |
| `*stim*` | Yes | Catches any directory with "stim" in the name (`stims`, `stimuli`, `cdp_stimuli`, `stimulus_set`, etc.) |
| Resolved path from `panel_stim_excludes` | If available | Exact match for a subject's real `stim_path` (from their `config.json`), for a stim dir that doesn't happen to have "stim" in the name |

`panel_stim_excludes` (`/home/bird/opdat/panel_stim_excludes`) is written by `rpioperantctl`, not `allsummary.py` itself — see Process Orchestration below.

**Straggler catch-up.** If a bird is swapped out of `panel_subject_behavior` between rsync cycles, the crontab may point at a different bird and any data from the previous bird collected between the last and current sync would be silently lost. To prevent this, `allsummary.py` tracks each run's box→bird mapping in `/home/bird/opdat/.allsummary_sync_state.json` and gives a departed bird one more pull, retried every cycle until it actually succeeds (so a box that happened to be unreachable exactly during a swap doesn't lose data either).

**Hardcoded paths** (no CLI flags — everything below is a constant at the top of the script):

| Constant | Path |
|---|---|
| `process_fname` | `/home/bird/opdat/panel_subject_behavior` |
| `OPDAT_ROOT` | `/home/bird/opdat/` |
| `STIM_EXCLUDES_FNAME` | `/home/bird/opdat/panel_stim_excludes` |
| `SYNC_STATE_FNAME` | `/home/bird/opdat/.allsummary_sync_state.json` |
| output | `/home/bird/all.summary` |

**Output format.** `all.summary` has one line per enabled box, always 9 tab-separated fields (box, bird, behavior, trials, feeds, timeouts, no-responses, feed errors, last-trial time) regardless of which case below applies — the dashboard's parser builds a fixed-width table from this file and breaks on any row with a different shape:

| Case | `last @ ...` field reads |
|---|---|
| Normal, with trial data today | `<timestamp> (N mins ago)` |
| `Lights`/`shape`/`pylights`/`lights.py` box (no trial concept) | `N/A (non-trial box)` |
| Subject has no `.summaryDAT` yet (brand new) | `N/A (new subject, no data yet)` |
| Real experiment, zero trials so far today | `N/A (no trials yet today)` |
| Any other/unexpected failure | `N/A (error, see allsummary.log)` |

`-avhW` on the rsync calls (specifically `-W`/`--whole-file`) is a deliberate choice, not an oversight: it trades bandwidth for CPU — a changed file gets resent in full rather than delta-transferred. Data integrity is unaffected either way (rsync verifies the transferred file against the source regardless of `-W`); it's purely an efficiency trade-off, and the lab's preference is minimizing server CPU load over bandwidth.

#### Process Orchestration (`rpioperantctl`)

Runs every 5 minutes via cron on the server:

```
*/5 * * * * /home/bird/code/rpioperantctl/rpioperantctl.py -psb_loc=/home/bird/opdat/panel_subject_behavior -s
```

For every row in `panel_subject_behavior` (enabled or not), it SSHes into that panel, checks `ps -ef`, and reconciles: starts the correct behavior if the panel's enabled and it isn't running; kills it if disabled but running; kills it if the *wrong* behavior is running regardless of enabled state.

**Editing the `panel_subject_behavior` config file is the preferred method for process control.**
 `rpioperantctl` treats this file as the single source of truth for what should be running on every box, and it re-asserts that truth every 5 minutes. That has a direct consequence: starting or stopping a behavior by hand — SSHing into a panel and running `nohup .../behave ... &`, or killing a process directly — only lasts until the next cron cycle. If the file doesn't agree with what you just did by hand, `rpioperantctl` will undo it: a manually-started process that doesn't match the file gets killed as "wrong behavior running"; a manually-killed process that the file still marks enabled gets restarted. This isn't a bug to work around — it's the whole point of the reconciliation loop, and it's why the file (not memory of what was last typed at an SSH prompt) has to be the actual record of intent. Always make the change in `panel_subject_behavior` first, then let `rpioperantctl` carry it out on its own schedule (or run it by hand with `-s -k` to apply immediately) — never the other way around.

**Flags:**

| Flag | Default | Meaning |
|---|---|---|
| `-s` | `False` | Start behaviors that should be running but aren't. Bare `-s` = `True`; accepts explicit `-s true`/`-s false` too |
| `-k` | `False` | Kill behaviors that shouldn't be running (wrong behavior, or disabled panel) |
| `-is_magpi` | `True` | Whether running directly on magpi.ucsd.edu vs. hopping through it from elsewhere |
| `-psb_loc` | `/home/bird/opdat/panel_subject_behavior` | Path to the panel/subject/behavior config file |
| `-stim_excludes_loc` | `/home/bird/opdat/panel_stim_excludes` | Where to write each panel's resolved stim exclude, for `allsummary.py` to read |

With no flags at all, it does a **dry run**, and prints what it would start/kill without doing either. The `panel_stim_excludes` write (see below) happens on every run regardless of `-s`/`-k`.

**Note** The crontab currently runs `-s` only, not `-k` — this is a deliberate, staged rollout, not an oversight. Without `-k`, a panel that ends up running the wrong behavior (its config changed but the old process was never manually killed) gets a *second*, correct-behavior process started alongside the still-running wrong one — both fighting over the same hardware. The decision to eventually add `-k` has been made; it's being held back specifically until everyone has updated their own entries in `panel_subject_behavior`, since `-k` isn't fail-safe the way `-s` is — a stale or inconsistent entry could get an actively-running, legitimate experiment killed the moment `-k` starts enforcing it. Check the live crontab (`crontab -l`) rather than assuming either state before making changes here.

**Stim-exclude resolution.** While it's already SSHed into each panel for the process check, `rpioperantctl` also reads that subject's `config.json` to resolve their real `stim_path` (explicit, or pyoperant's own default of `<experiment_path>/stims`), and writes the result to `panel_stim_excludes` (tab-separated: panel, subject, exclude-path-relative-to-the-subject's-own-folder) for `allsummary.py` to consume — this avoids `allsummary.py` needing its own separate SSH connection to redo the same lookup every 15 minutes.

#### Mail Relay

MagPi clients have no direct internet access, so PyOperant's error-notification emails (sent via `SMTPHandler` in `pyoperant/behavior/base.py`, using each subject's `experimenter.email` as the recipient) relay through the MagPi server rather than going out directly. Each client's local config file (`local_pi_revd.py`, `local_pi_revc.py`, etc.) already points at the server:

```
SMTP_CONFIG = {'mailhost': '192.168.1.100', ...}
```

The server relays outbound through UCSD's mail infrastructure (`outbound.ucsd.edu`), which trusts the server's on-campus IP directly — no authentication is required anywhere in the chain, on the server or on any client.

For this to work, the server's Postfix has to accept connections from the MagPi subnet, which is not the default:

```
inet_interfaces = all
mynetworks = 127.0.0.0/8, 192.168.1.0/24
```

As noted at the top of this section, this is CFEngine-managed — request the network permission from SSCF rather than editing `main.cf` directly (a live edit not backed by a matching policy change gets silently reverted within minutes; this happened once). This was granted for the MagPi subnet in July 2026.

To test the relay end-to-end without needing a client, connect directly to the server's LAN-facing address and walk through the SMTP conversation by hand — this exercises the same path a client's SMTP call would use:

```
nc 192.168.1.100 25
EHLO test-client
MAIL FROM:<bird@magpi.ucsd.edu>
RCPT TO:<you@ucsd.edu>
DATA
Subject: relay test
(blank line, then a body line, then a line with just a period)
QUIT
```

A 220 greeting and 250 responses to MAIL FROM/RCPT TO confirm the server is accepting the connection; the message actually arriving confirms the full outbound path.

**Configuring email notifications for a subject.** Two things have to both be set in that subject's `config.json`:

| Setting | Location | Effect if missing/invalid |
|---|---|---|
| `"email"` in `log_handlers` | top-level config.json list | If absent, nothing is emailed regardless of the field below — everything just goes to the local `.log` file. |
| `experimenter.email` | `experimenter` object | If `"email"` is in `log_handlers` but this is missing or empty, email notifications are disabled for that session (logged as a warning, not a crash) — as of July 2026; a config written before that fix would have crashed the whole experiment on startup instead. |

When both are set correctly, *any* `WARNING`/`ERROR`/`CRITICAL`-level log call anywhere in the running process is a candidate for email — not just deliberate "notify" calls. This includes: uncaught exceptions, the structured hardware-error callback (`InterfaceError`/`ComponentError`), hopper malfunction warnings, and `shape.py`'s block-progress messages. Every one of these always reaches the local `.log` file regardless of what follows.

**Not every candidate actually sends an email, though.** To avoid overwhelming the experimenter with routine, low-value notifications (a flaky hopper generating one email per hiccup, for instance), a threshold filter sits in front of the email handler:

| Always emails immediately | Only emails after recurring |
|---|---|
| `CRITICAL` records (hardware failures via the structured callback) | Everything else (routine `WARNING`/`ERROR` calls — e.g. hopper hiccups) |
| Unhandled top-level exceptions (these may be the last thing the process ever logs before crashing, so they can't wait for a "next occurrence") | Threshold is `EMAIL_OCCURRENCE_THRESHOLD` (3) recurrences of the *same call site* (grouped by module + function, not exact message text — different hopper errors from the same check don't reset each other's count) |
| `shape.py`'s block-progress messages (kept real-time so the experimenter can track shaping progress) | Once the threshold is hit, later occurrences from that same call site keep emailing too, not just the 3rd one |

This is occurrence-count only for now — no time-window escalation (e.g. an issue that recurs slowly over hours doesn't get bumped up before hitting the raw count). That's a known simplification, not an oversight; can be refined later if needed.

The email subject line includes the sending box's hostname (e.g. `[pyoperant notice] on magpi04`), so notifications from multiple boxes can be discriminated; the body includes the bird ID, log level, and timestamp.

#### Dashboard (`websitebehavior`)

Runs every 15 minutes via cron on the server, through a small wrapper that activates the right conda environment first:

```
*/15 * * * * /home/bird/code/websitebehavior/daily_website.sh > /home/bird/code/websitebehavior/log.out 2>&1
```

`daily_website.sh` just sets `PATH` to a dedicated conda env (`websiteupdate_36`) and runs `website_update_cron.py`. That script reads `all.summary` (Data Aggregation's output — this is why Data Aggregation has to run first, and why the two cron lines share the same 15-minute cadence) and `panel_subject_behavior`, renders per-bird plots and status tables, and writes a single `behav.php` file, which it then pushes off-box:

```
scp behav.php starling@psych-labs.ucsd.edu:/home/websites/gentnerlab/behavior/behav.php
```

**The dashboard** is hosted on `psych-labs.ucsd.edu` (managed by sscf-psych), not magpi.ucsd.edu. The MagPi server only *generates* the page and pushes it to psych-labs; nothing about the dashboard itself runs on the MagPi server. This push requires its own SSH key trust from magpi.ucsd.edu to `starling@psych-labs.ucsd.edu`, independent of anything else in this chapter.

**Access the dashboard via gentnerlab.ucsd.edu/behavior**, using a shared, hardcoded password not a per-user account or AD credentials.

**Other known debt in this repo**, for whoever picks it up next: Google Calendar OAuth credentials (`credentials/credentials.json`, `token.pickle`, used for the bird-duty scheduling feature) are committed directly to git history — there's no `.gitignore` in the repo at all, so compiled files and logs get tracked too. The environment is Python 3.6 (end-of-life since Dec 2021), and `requirements.txt` pulls one dependency via `git+git://github.com/gentnerlab/behav-analysis.git` — GitHub disabled the unauthenticated `git://` protocol years ago, so this dependency likely can't be installed fresh into a new environment without editing that line to `git+https://` or `git+ssh://` first.

**Other things it does**, beyond the main status table: pulls a Google Calendar (via `calendar_utils.py`) to render a bird-duty schedule on the dashboard, and supports per-experimenter custom plots (`custom_plots.py` imports named plotting functions out of `custom_plotting/`, e.g. `custom_plotting/tims.py`, `custom_plotting/annas.py`) for anyone who wants a non-default view of their own bird's data.

### 5.3 The panel_subject_behavior File

The panel_subject_behavior file (located at /home/bird/opdat/panel_subject_behavior on the server) is the central configuration table for the whole system — both `allsummary.py` and `rpioperantctl` read it. It has one row per operant box with five whitespace-delimited columns:

|            |                                                     |                                        |
| ---------- | --------------------------------------------------- | -------------------------------------- |
| **Column** | **Example**                                         | **Description**                        |
| 1          | magpi03                                             | Box hostname (panel ID)                  |
| 2          | 1                                                   | Enable flag: 1 = active, 0 = disabled  |
| 3          | 1234                                                | Bird ID number (bare number, no "B" prefix) |
| 4          | opdat/B\<3\>                                        | Data directory template — `<3>` is replaced with column 3's value |
| 5          | behave -P \<1\> -S B\<3\> TwoAltChoiceExp           | Behavior command template — `<3>` and `<1>` (panel number) get substituted |

Lines beginning with \# are treated as comments. A typical entry looks like:

```
magpi03 1 1234 opdat/B<3> behave -P <1> -S B<3> TwoAltChoiceExp
```

After substitution, this resolves to a data directory of `opdat/B1234` and a command of `behave -P 1 -S B1234 TwoAltChoiceExp`. The last whitespace-separated token of column 5 (after substitution) is the actual behavior/protocol name — this is what both `allsummary.py` (to detect non-trial `Lights`/`shape` boxes) and `rpioperantctl` (to compare against `ps -ef` output) key off of, not the literal word "behave".

### 5.4 Firewall Requirements

The MagPi server's firewall (managed by CFEngine/SSCF) must allow the following inbound connections from the 192.168.1.0/24 subnet:

  - UDP on NTP port 123 — for time synchronization from clients

  - TCP on SSH port 22 — for git clones and remote login from clients

  - TCP on SMTP port 25 — for clients (and the server itself) to relay error-notification email through the server (see Mail Relay above)

These must be explicitly requested from SSCF. Without the NTP rule, clocks on clients will drift and timestamps will be unreliable. Without the SSH rule, clients cannot pull code updates from the server. Without the SMTP rule, mail relay attempts fail with a plain connection-refused error.

The server's own network config (interfaces, routing) is managed via netplan with the NetworkManager renderer — `netplan-eno1`/`netplan-eno2` connections, config files under `/etc/netplan/`. Editing network settings live with `nmcli` doesn't stick for netplan-owned settings; changes have to go into the YAML file itself, then `sudo netplan generate && sudo netplan apply`.

## 6. Software Setup

This chapter covers how to install PyOperant on the MagPi client and how to configure a panel in local\_pi\_revd.py or local\_pi\_revc.py.

### 6.1 Installing PyOperant

PyOperant requires Python 3 and pigpio. The last Python 2.7-compatible release is tagged V2-final on GitHub (github.com/gentnerlab/pyoperant/releases/tag/V2-final). All instructions in this manual refer to the Python 3 codebase on master. If you need to run the legacy Python 2.7 version, check out that tag, but be aware it is no longer maintained.

#### Python 3 environment setup

Raspberry Pi OS (Bullseye or later) includes Python 3 by default. Verify before starting:

```
python3 --version
```

Install system dependencies. Note that the Python 3 package names differ from the Python 2 equivalents: use python3, python3-dev, and python3-pip instead of python and python-dev. The ephem package replaces pyephem:

```
sudo apt install python3 python3-dev python3-pip portaudio19-dev pigpio
pip3 install pyaudio ephem
```

Start the pigpio daemon and enable it on boot:

```
sudo pigpiod
sudo systemctl enable pigpiod
```

Clone the PyOperant repository from the MagPi server and install:

```
git clone bird@192.168.1.100:~/code/pyoperant ~/pyoperant
cd ~/pyoperant && pip3 install -e .
```

Do the same for py-behaviors:

```
git clone bird@192.168.1.100:~/code/py-behaviors ~/py-behaviors
cd ~/py-behaviors && pip3 install -e .
```

Verify the installation:

```
python3 -c "import pyoperant; print('pyoperant ok')"
python3 -c "import pigpio; print('pigpio ok')"
python3 -c "import pyaudio; print('pyaudio ok')"
```

The -e flag installs in editable mode, meaning changes to the source files take effect immediately without reinstalling. Use pip3 (not pip) throughout to ensure packages are installed for Python 3.

### 6.2 The Local Config System and Board Revision Detection

PyOperant uses a two-stage routing system to load the correct hardware configuration for the machine it is running on. The entry point is pyoperant/local.py, which first checks the hostname to distinguish between machine families (zog, vogel, MagPi), then for MagPi clients performs a second check to determine the board hardware revision.

#### Stage 1: Hostname Routing

The file pyoperant/local.py reads socket.gethostname() and imports the matching config:

  - Hostname contains ‘vogel’ → imports local\_vogel.py (legacy Comedi-based hardware)

  - Hostname contains ‘zog’ → imports local\_zog.py (legacy Comedi-based hardware)

  - Hostname contains ‘pi’ → proceeds to Stage 2 (MagPi clients, both Rev C and Rev D)

#### Stage 2: Board Revision Detection

All MagPi clients have hostnames containing ‘magpi’ (e.g. magpi03, magpi14). Because both Rev C and Rev D boards use the same hostname pattern but have different hardware — Rev C has a solenoid-driven hopper, Rev D has a servo-driven hopper with a second PCA9685 chip — using the hostname alone to select config would be unreliable. Instead, each MagPi client has a plain-text file at /etc/magpi\_revision that explicitly declares its board version:

```
# On a Rev D board:
echo 'revd' | sudo tee /etc/magpi_revision
# On a Rev C board:
echo 'revc' | sudo tee /etc/magpi_revision
```

local.py reads this file and imports the correct config:

  - revc → imports local\_pi\_revc.py (solenoid hopper, GPIO 16 output)

  - revd → imports local\_pi\_revd.py (servo hopper, second PCA9685 at 0x45)

If the file is missing or contains an unrecognized value, PyOperant raises a RuntimeError with a clear message before anything is driven, preventing hardware mismatches.

> *This file must be set once on each MagPi client during initial setup. See Section 7.1 for the full setup procedure.*

#### What the Local Config Does

Whichever local config is loaded, it does the same three things:

  - Creates an instance of RaspberryPiInterface (which connects to pigpio and sets up the PCA9685 chip or chips).

  - Creates hwio channel objects (BooleanInput, BooleanOutput, PWMOutput) and assigns them to physical pin or channel numbers.

  - Creates Component objects (Hopper, PeckPort, HouseLight, etc.) using those hwio channels, and assembles them into a Panel.

The Hopper component is constructed differently depending on the board revision, but all other components are identical between Rev C and Rev D.

### 6.3 Configuring a Panel

The following annotated example shows the key differences between local\_pi\_revd.py (Rev D) and local\_pi\_revc.py (Rev C). Both files follow the same four-step pattern; only the hopper wiring differs.

Step 1: Define channel constants

Both files declare channel assignments as named constants at the top. This is the only place GPIO pin or PCA9685 channel numbers appear — the panel class below refers to them by name.

```
# Rev D (local_pi_revd.py)
INPUTS = [5, 6, 13, 26, 23, 24, 25, 9, 11, 10] # Hopper IR, L/C/R IR, AUX IR 1-6
LIGHTS_PCA9685_ADDRESS = 0x55 # U1: A0, A2, A4 pulled high
SERVO_PCA9685_ADDRESS = 0x45 # U7: A0, A2 pulled high
HOPPER_SERVO_CHANNEL = 0 # HOPPER_CTL on U7 (PCA9685 at 0x45)
AUX_SERVO_OUTPUTS = [1, 2, 3, 4] # AUX_SERVO_1-4 on U7
PWM_OUTPUTS = [0,1,2,3,4,5,6,7,8,9,10,13,14,15] # channels 11,12 not connected on Rev D
# Rev C (local_pi_revc.py)
INPUTS = [5, 6, 13, 26, 23, 24, 25, 9, 11, 10] # same as Rev D
OUTPUTS = [16] # Hopper solenoid on GPIO 16
PWM_OUTPUTS = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15] # all 16 channels connected on Rev C
```

Step 2: Create the interface

```
self.interfaces['raspi_gpio_'] = raspi_gpio_.RaspberryPiInterface(device_name='pi', lights_address=LIGHTS_PCA9685_ADDRESS, # Rev D: also pass servo_address=SERVO_PCA9685_ADDRESS )
```

On Rev D this initializes both PCA9685 chips: the lights chip (U1, 0x55, 1000 Hz) and the servo chip (U7, 0x45, 50 Hz). On Rev C only the lights chip is initialized.

Step 3: Create hwio channel objects

```
# Both revisions: IR inputs and PWM light outputs
for in_chan in INPUTS:
self.inputs.append(hwio.BooleanInput(interface=raspi, params={'channel': in_chan}))
for ch in PWM_OUTPUTS:
self.pwm_outputs.append(hwio.PWMOutput(interface=raspi, params={'channel': ch}))
# Rev D only: servo output and auxiliary servo outputs
self.hopper_servo = hwio.PWMOutput(interface=raspi,
params={'channel': HOPPER_SERVO_CHANNEL, 'servo': True})
self.aux_servos = [hwio.PWMOutput(interface=raspi, params={'channel': ch, 'servo': True})
for ch in AUX_SERVO_OUTPUTS]
# Rev C only: solenoid output
self.outputs = [hwio.BooleanOutput(interface=raspi, params={'channel': 16})]
```

Step 4: Assemble components

Peck ports, house light, and RGB cue light are identical between revisions. Only the Hopper constructor differs:

```
# Rev D: servo hopper
self.hopper = components.Hopper(IR=self.inputs[0], servo=self.hopper_servo,
up_angle=45, down_angle=10, inverted=True)
# Rev C: solenoid hopper
self.hopper = components.Hopper(IR=self.inputs[0], solenoid=self.outputs[0], inverted=True)
# Both revisions: RGB cue light
# Rev D indices 11/12/13 = channels 13/14/15 (channels 11,12 skipped in PWM_OUTPUTS)
# Rev C indices 13/14/15 = channels 13/14/15 (all channels present)
self.cue = components.RGBLight(red=self.pwm_outputs[-3],
green=self.pwm_outputs[-2],
blue=self.pwm_outputs[-1], name='cue')
```
> *The up\_angle and down\_angle values shown (45 and 10) are placeholders in degrees. These must be tuned empirically for each physical panel. See Section 6.4 for the tuning procedure.*

### 6.4 Tuning Servo Angles (Rev D only)

This section applies only to Rev D boards with servo-driven hoppers. Rev C boards with solenoid hoppers have no angles to tune.

The up\_angle and down\_angle values for the hopper servo must be determined empirically for each panel. They are angles in degrees (0.0 to 300.0) corresponding to the full travel range of the goBILDA 25-2 servo. The interface converts degrees to microsecond pulse widths internally (0° = 500 µs, 300° = 2500 µs). Values will differ between panels due to mechanical variation in how the servos are mounted. The values must be tuned once per panel and recorded in local\_pi\_revd.py.

#### 6.4.1 Using the Tuning Script

The tuning script tune\_servo.py lives in the scripts/ directory of the pyoperant repository and is installed on the PATH automatically when you run pip install -e . After installation it can be invoked directly:

```
sudo pigpiod # ensure pigpiod is running
python tune_servo.py
```

The script connects to the servo chip and IR beam sensor and presents an interactive prompt. The available commands are:

```
<number> move servo to that angle in degrees (e.g. 45.0)
u move to current up_angle
d move to current down_angle
su set current angle as up_angle
sd set current angle as down_angle
i read IR beam status
f run a full feed cycle with the current angles
q quit and print final values
```

#### 6.4.2 Step-by-Step Tuning Procedure

**Step 1 — Find down\_angle.** Start with a low angle (try 10.0 degrees). Enter values until the hopper tray is fully lowered and clear of the feed opening. The IR beam should read CLEAR. Confirm with i, then type sd to set the value.

**Step 2 — Find up\_angle.** Try higher values (start around 45.0 degrees) until the tray is fully raised and a subject could access the food. The IR beam should read BROKEN (beam tripped by the raised tray). Confirm with i, then type su to set the value.

**Step 3 — Check servo limits.** Use u and d to cycle between the two positions several times. Listen for the servo straining or buzzing at either end of travel. If it strains, adjust the offending angle away from the limit until the servo moves cleanly and quietly. Never exceed the safe hardware pulse width limits (see Appendix B).

**Step 4 — Run a full feed cycle.** Type f. The script will raise the hopper, confirm the IR beam is tripped, wait 2 seconds, lower the hopper, and confirm the IR beam clears. If either confirmation fails, adjust the relevant angle and repeat until the full cycle passes cleanly.

**Step 5 — Record the values.** Type q. The script prints the exact Hopper constructor call to copy into local\_pi\_revd.py. Update the up\_angle and down\_angle for this panel and save the file. Repeat this procedure for every Rev D panel — the values will differ between panels.

### 6.5 Verifying the Panel

Before running an experiment, always verify that the panel is working correctly. The test\_panel.py script auto-detects the board revision from /etc/magpi\_revision, initializes the panel, and runs a two-phase test (autonomous component check followed by interactive user confirmation):

```
python3 scripts/test_panel.py
```

The script runs Phase 1 autonomously (house light, LEDs, hopper, speaker) then prompts you to confirm each component visually and verify IR beam detection. Fix any failures before proceeding.

## 7. System Setup and Usage

This chapter covers everything needed to bring a new MagPi client online and get an experiment running: flashing the SD card, configuring the network, deploying code, and the day-to-day workflow for adding birds and starting sessions.

### 7.1 Preparing a New MagPi Client

#### Flashing the SD Card

A pre-made Raspbian Lite image with the base RPiOperant configuration is stored on the MagPi server at /mnt/cube/RPiOperantOS.img. To flash a new SD card:

15. Insert the blank SD card into a computer.

16. Find the device name: lsblk

17. Unmount the card if it auto-mounted.

18. Copy the image (replace /dev/sdX with your device):

```
sudo dd if=/mnt/cube/RPiOperantOS.img of=/dev/sdX bs=4M
```

19. Insert the SD card into the MagPi client.

#### Initial Configuration

Assume the new box number is XX (e.g., 03, 14). Boot the Pi with it connected to the LAN switch.

20. Log in: ssh bird@192.168.1.1 (default IP before hostname is set), password starling

21. Set the hostname: sudo raspi-config → Network Options → Hostname → magpiXX

22. Expand the filesystem: sudo raspi-config → Advanced Options → Expand Filesystem

23. Reboot: sudo reboot

24. Log back in: ssh bird@magpiXX

25. Set the static IP address: sudo vim /etc/network/interfaces

```
auto eth0
iface eth0 inet static
address 192.168.1.XX
netmask 255.255.255.0
gateway 192.168.1.100
```

26. Reboot. The box is now accessible at 192.168.1.XX.

27. Verify the time has synchronized: date

#### Deploying Code

Run the following on the MagPi client (all from the bird user’s home directory):

28. Remove any stale pyoperant clone and reclone from the server:

```
rm -rf ~/pyoperant
git clone bird@192.168.1.100:~/code/pyoperant ~/pyoperant
```

29. Install in editable mode:

```
cd ~/pyoperant && pip install -e .
```

30. Do the same for py-behaviors:

```
rm -rf ~/py-behaviors
git clone bird@192.168.1.100:~/code/py-behaviors ~/py-behaviors
cd ~/py-behaviors && pip install -e .
```

31. Start the pigpio daemon and add it to startup:

```
sudo pigpiod
sudo systemctl enable pigpiod
```

#### Verifying the Hardware

32. Run i2cdetect -y 1. You should see two devices: 0x55 (lights PCA9685) and 0x45 (servo PCA9685). If either is missing, check the board wiring and re-solder if needed.

33. Connect the 50-pin IDC ribbon cable and audio cable to the operant panel.

34. Run the panel test (it auto-detects the board revision from /etc/magpi\_revision):

```
python3 scripts/test_panel.py
```

All components should cycle without errors. Fix any failures before placing a bird.

### 7.2 Setting Up a New Behavior

Suppose your behavior class is called MyBehav and lives in the file my\_behav.py. Do the following on the MagPi server (not on the clients directly):

35. Copy the behavior script into py-behaviors:

```
cp ~/my_behav.py ~/code/py-behaviors/glab_behaviors/my_behav.py
```

36. Register it in the package \_\_init\_\_.py:

```
echo 'from my_behav import MyBehav' >> ~/code/py-behaviors/glab_behaviors/__init__.py
```

37. Copy your default configuration file:

```
cp ~/my_config.json ~/code/py-behaviors/example_configs/
```

38. Commit and push to GitHub master:

```
cd ~/code/py-behaviors
git add -A && git commit -m 'Add MyBehav' && git push origin master
```

Clients will pick up the change the next time they run git pull origin master.

### 7.3 Setting Up a New Bird

Make sure the panel hardware (cage, lights, hopper) is in place and the panel test passes before setting up software for a new bird.

39. Log in to the target client: ssh bird@magpiXX

40. Verify pyoperant and py-behaviors are up to date:

```
cd ~/pyoperant && git pull origin master
cd ~/py-behaviors && git pull origin master
```

41. Create the bird’s data directory:

```
mkdir -p ~/opdat/BXXXX/Stimuli
```

42. Copy the config file and stimuli into the bird’s folder:

```
cp ~/py-behaviors/example_configs/my_config.json ~/opdat/BXXXX/config.json
```

Edit config.json to set the correct bird ID, experimenter, stimulus paths, and any behavior-specific parameters.

43. If starting with shaping, set shape to 'block1' in config.json.

44. On the MagPi server, open panel\_subject\_behavior and add or update the row for this box. Follow the exact column format from Section 5.3 — column 3 is a **bare** bird number (no `B` prefix; the tools prepend it), column 4 is the `opdat/B<3>` template, and the behavior/protocol name must be the **last** token of the command column (both `allsummary.py` and `rpioperantctl` identify the protocol from that final token):

```
vim ~/opdat/panel_subject_behavior
# panel enable birdID datadir command
magpiXX 1 XXXX opdat/B<3> behave -P <1> -S B<3> TwoAltChoiceExp
```

45. `rpioperantctl` will start the behavior on its next 5-minute cron cycle (Section 5.2). To apply immediately without waiting, run it by hand on the server:

```
/home/bird/code/rpioperantctl/rpioperantctl.py -s
```

46. Verify it started correctly:

```
ssh bird@192.168.1.XX
tail -f ~/opdat/BXXXX/BXXXX.log
```

The house lights should be on and shaping block 1 (free hopper access every 30 seconds) should begin. If you see errors in the log, check the config file and hardware before proceeding.

### 7.4 Day-to-Day Monitoring

From the MagPi server you can check all boxes at a glance by running rpioperantctl with no action flags, which does a dry run — reporting what it would start or kill without changing anything:

```
/home/bird/code/rpioperantctl/rpioperantctl.py
```

To follow a specific box’s log in real time:

```
ssh bird@192.168.1.XX 'tail -f ~/opdat/BXXXX/BXXXX.log'
```

The all.summary file (updated every 15 minutes by the server’s cron job) gives a one-line status for every bird: trials run, feeds delivered, hopper failures, and the time of the last trial:

```
cat ~/opdat/all.summary
```

### 7.5 Updating Code on Clients

To push a code update to all active clients:

47. Update the server’s local clone by pulling the change from GitHub onto the server (or commit it directly on the server):

```
cd ~/code/pyoperant && git pull origin master
```

48. SSH into each client and pull:

```
ssh bird@192.168.1.XX
cd ~/pyoperant && git pull origin master && pip install -e .
```

Changes to behavior scripts in py-behaviors follow the same pattern. It is not necessary to restart a running experiment to pick up Python changes, but changes to local\_pi\_revd.py, local\_pi\_revc.py, or raspi\_gpio\_.py require restarting PyOperant.

### 7.6 Stopping and Restarting Experiments

The `panel_subject_behavior` table is the source of truth (Section 5.2): the cleanest way to stop or start a box is to edit its enable flag and let `rpioperantctl` reconcile on its next 5-minute cron cycle. The commands below apply the same changes immediately from the MagPi server. Note that `-k` only kills processes the table says should **not** be running (wrong behavior, or a disabled panel) — it does not blindly kill everything, so "stopping" a box means first marking it disabled in the table.

To stop all experiments across all boxes (for maintenance, cage cleaning, etc.), set every enable flag to 0 (or comment the rows out) in panel\_subject\_behavior, then run with `-k`:

```
/home/bird/code/rpioperantctl/rpioperantctl.py -k
```

`-k` sends SIGTERM to each behave process that shouldn't be running, which triggers session\_post and saves data before exiting.

To disable a specific box without touching others, set its enable flag to 0 in panel\_subject\_behavior and run:

```
/home/bird/code/rpioperantctl/rpioperantctl.py -k
```

To (re)start everything according to the panel\_subject\_behavior table:

```
/home/bird/code/rpioperantctl/rpioperantctl.py -s
```

To kill stale processes and start correct ones in a single pass, combine both flags:

```
/home/bird/code/rpioperantctl/rpioperantctl.py -s -k
```
> *Give session\_post a moment to finish writing data on a box that was mid-trial before it is restarted. Also note the every-5-minute cron job runs with `-s` only (Section 5.2), a deliberate staged rollout — running `-k` by hand is how kills are enforced until that changes.*

## 8. Using Existing Protocols

The lab maintains a private repository of behavioral protocols called py-behaviors (installed as the Python package glab\_behaviors). It lives on the MagPi server and is cloned onto each client alongside pyoperant. All protocols in the package are subclasses of TwoAltChoiceExp and follow the same config.json-driven interface described in Section 10.5.

The repository is located at:

```
~/code/py-behaviors # on the MagPi server
~/py-behaviors # on each MagPi client
```

To install or update on a client:

```
cd ~/py-behaviors && git pull origin master
pip install -e .
```

#### Available Protocols

The following protocols are currently in the package:

|                                            |                                                                                                                                                                                       |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Class**                                  | **Description**                                                                                                                                                                       |
| Basic\_2AC                                 | Standard two-alternative choice task. Randomly samples from left and right stimulus sets each session. The simplest starting point for a new discrimination experiment.               |
| song\_recognition                          | Two-alternative choice task for song recognition. Randomly samples from left and right stimulus sets; supports per-trial index tracking for parametric stimulus sets.                 |
| SameDifProbs                               | Same/different discrimination with probabilistic stimulus presentation. The animal hears two motifs and responds left (same) or right (different). Supports mirrored side assignment. |
| SameDifProbs2                              | Variant of SameDifProbs with modified block structure.                                                                                                                                |
| SameDifProbs3                              | Variant of SameDifProbs using dynamically generated stimuli from a song grammar.                                                                                                      |
| ABCategory / ABCategory2                   | Category discrimination tasks using A/B stimulus sets with configurable same/different trial types.                                                                                   |
| cue\_probability                           | Two-alternative choice with interpolated stimuli along a continuum. Cue reliability is controlled by a probability parameter (cue\_prob).                                             |
| cue\_probability\_multicue                 | Extension of cue\_probability supporting multiple simultaneous acoustic cues.                                                                                                         |
| cue\_probability\_multicue\_predict\_morph | Further extension supporting morphed stimuli for cue prediction experiments.                                                                                                          |
| CueSwitchExperiment                        | Two-alternative choice where the relevant cue dimension switches across sessions.                                                                                                     |
| EvidenceAccumExperiment                    | Evidence accumulation task. Stimuli are sequences of motifs; the animal integrates evidence across motifs before responding. Supports triangular block designs.                       |
| EvidenceAccumExperimentBT                  | Variant of EvidenceAccumExperiment with a between-trial structure.                                                                                                                    |
| DelayedMatch2                              | Delayed match-to-sample. Presents a sample motif, a delay, then a test motif. The animal responds same or different.                                                                  |
| FirstOrder                                 | First-order Markovian sequence discrimination. Stimuli are generated from a first-order Markov grammar.                                                                               |
| SecondOrder                                | Second-order Markovian sequence discrimination.                                                                                                                                       |
| TwoACMatchingExp                           | Two-alternative matching task with configurable stimulus-response mapping.                                                                                                            |
| TwoAC\_easy                                | Simplified two-alternative choice for early training, using pure-tone stimuli before transitioning to natural stimuli.                                                                |
| TwoAC\_withGrammar                         | Two-alternative choice with grammatically structured stimulus sequences.                                                                                                              |
| TwoAC\_GrammarMorphs                       | Variant of TwoAC\_withGrammar using morphed grammar stimuli.                                                                                                                          |
| TwoAC\_RecGram                             | Two-alternative choice for recursive grammar discrimination.                                                                                                                          |
| TwoAC\_MFDiscrim                           | Male/female discrimination task.                                                                                                                                                      |
| TwoAC\_TempoMod                            | Temporal modulation discrimination task.                                                                                                                                              |
| TwoAC\_Quant                               | Quantification task variant.                                                                                                                                                          |
| TwoAC\_TileTest                            | Tiled stimulus test variant.                                                                                                                                                          |
| DiagnosticTransitionsExp                   | Diagnostic transitions experiment for sequence learning.                                                                                                                              |
| PairedAssoc                                | Paired associates task. The animal learns arbitrary stimulus-response associations.                                                                                                   |
| first\_last\_match                         | First/last element matching task for sequence processing.                                                                                                                             |
| long\_dependency                           | Long-distance dependency discrimination for sequence grammar experiments.                                                                                                             |
| soundtexture\_2AC                          | Two-alternative choice using sound texture stimuli.                                                                                                                                   |
| XYContext                                  | Contextual two-alternative choice with XY stimulus pairs.                                                                                                                             |
| text\_markov / text\_markov\_word          | Markov chain text generation tasks (research/development use).                                                                                                                        |

#### How the Protocols Relate to TwoAltChoiceExp

Every protocol in glab\_behaviors inherits from TwoAltChoiceExp and extends it by overriding session\_post and adding stimulus-building methods. The general pattern is:

  - \_\_init\_\_ calls super().\_\_init\_\_() to set up the base experiment, then calls a pre\_block() or build\_block() method to populate self.parameters\['block\_design'\]\['blocks'\]\['default'\]\['conditions'\] with the trial list for the first session.

  - session\_post resets parameters to their starting values, rebuilds the trial list for the next session, and returns None to signal that the session is complete.

  - Stimulus-building methods (get\_conditions, get\_motifs, build\_block, build\_wavs, etc.) are defined per-protocol and called from both \_\_init\_\_ and session\_post.

This means all glab\_behaviors protocols use the same config.json parameters as TwoAltChoiceExp (Section 10.5), plus any additional protocol-specific parameters documented below.

#### Using an Existing Protocol

To run Basic\_2AC on bird B1234 from box 1:

```
behave Basic_2AC -P 1 -S B1234 -c config.json
```

A minimal config.json for Basic\_2AC looks like this:

```
{
"experimenter": {"name": "Your Name", "email": "yourname@ucsd.edu"},
"subject": "B1234",
"panel_name": "1",
"experiment_path": "/home/pi/opdat/B1234",
"stim_path": "/home/pi/opdat/B1234/stimuli",
"light_schedule": "sun",
"response_win": 5.0,
"intertrial_min": 5.0,
"correction_trials": true,
"shape": false,
"debug": false,
"log_handlers": ["email"],
"current_available_motifs": 10,
"left_stims": {"0": "A01.wav", "1": "A02.wav"},
"right_stims": {"0": "B01.wav", "1": "B02.wav"},
"category_conditions": [
{"class": "L"},
{"class": "R"}
],
"stims": {},
"classes": {
"L": {"component": "left", "reward_value": 2.0, "punish_value": 10.0},
"R": {"component": "right", "reward_value": 2.0, "punish_value": 10.0}
},
"block_design": {
"blocks": {"default": {"queue": "block", "conditions": []}},
"order": ["default"]
},
"reinforcement": {"schedule": "percent_reinf", "prob": 0.4, "secondary": true}
}
```

#### Writing a New Protocol for the Repository

When you write a new protocol that others in the lab will use, add it to py-behaviors rather than keeping it in pyoperant. The steps are:

  - Create your class file in \~/code/py-behaviors/glab\_behaviors/ on the MagPi server.

  - Add an import line to \~/code/py-behaviors/glab\_behaviors/\_\_init\_\_.py so behave can find it.

  - Commit and push to the server’s git repo so other clients can pull it.

  - Add an example config.json to \~/code/py-behaviors/example\_configs/ for future reference.

On the clients, pull and reinstall:

```
cd ~/py-behaviors && git pull origin master && pip install -e .
```
> *glab\_behaviors has been migrated to Python 3 alongside pyoperant — every protocol in the package parses and imports cleanly under Python 3, and the package uses explicit relative imports in \_\_init\_\_.py. If you are adapting an older protocol that was written for the Python 2 codebase, apply the same fixes catalogued in Appendix C (print(), except ... as, range/input, relative imports) before adding it.*

## 9. Running Experiments and Troubleshooting

### 9.1 Starting a Session

Before starting any session, go through this checklist in order:

  - Confirm pigpiod is running: sudo pigpiod

  - Confirm the panel is clean and has fresh food loaded.

  - Run python3 scripts/test\_panel.py and confirm all components pass.

  - Check that the stimulus files exist at the paths specified in the config.

  - Check that the data output directory exists and is writable.

  - Place the subject in the panel.

  - Start the experiment: behave TwoAltChoiceExp -P 1 -S B1234 -c config.json

See Section 10.4 for a full description of the behave command arguments and Section 10.5 for config.json parameters.

### 9.2 Monitoring a Running Session

PyOperant logs trial-by-trial output to a log file in the subject’s experiment\_path. Follow it in real time:

```
tail -f /home/pi/opdat/bird42/bird42.log
```

If the log goes silent for more than a few minutes, check whether the subject is still active and whether any hardware errors have been raised.

### 9.3 Common Errors and Solutions

|                         |                                                                                                                                                           |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Error**               | **What to do**                                                                                                                                            |
| HopperWontComeUpError   | The servo moved but the IR beam was not tripped. Check that up\_angle is large enough to fully raise the hopper. Check IR beam alignment and connections. |
| HopperWontDropError     | IR beam still tripped after servo moved to down\_angle. Check that down\_angle is small enough. Check for physical obstruction.                           |
| HopperAlreadyUpError    | Hopper was raised at the start of a feed. A previous feed did not complete cleanly. Call panel.reset() to recover.                                        |
| pigpio not connected    | pigpiod is not running. Run: sudo pigpiod                                                                                                                 |
| I2C device not found    | PCA9685 chip not visible on I2C bus. Check wiring. Run: i2cdetect -y 1 to see which addresses are responding.                                             |
| Only one PCA9685 found  | The servo chip (0x45) is missing. Check that address pins A0 and A2 on U7 are pulled high. Resolder if needed.                                            |
| No audio output         | Check PortAudio is installed and correct device selected. Run: python -c "import pyaudio; p = pyaudio.PyAudio(); print(p.get\_device\_count())"           |
| Green power LED not lit | A supply rail is below threshold. Check the input power supply voltage and all Molex connections before proceeding.                                       |

### 9.4 Ending a Session

Sessions end automatically when session\_post is reached. The panel is reset, data is saved, and the experiment returns to the idle state to wait for the next session window.

To end early, press Ctrl+C. PyOperant catches the interrupt and attempts to run session\_post before exiting. Always check the log and data file afterwards.

### 9.5 After the Session

  - Remove the subject from the panel.

  - Check the data file to confirm trials were logged correctly.

  - Clean the panel (remove uneaten food, wipe the chamber).

  - Reset the panel: panel.reset()

  - Back up the data to the lab server.

## 10. Writing Your Own Experiment

This chapter walks through how to write a behavioral protocol in PyOperant from scratch, using a simple go/no-go auditory discrimination task as an example.

### 10.1 Choosing a Base Class

Before writing any code, check whether the experiment you want to run already exists in the lab’s py-behaviors repository (glab\_behaviors). This repository contains over 25 ready-to-use behavioral protocols that cover the most common paradigms used in the lab. Using an existing protocol saves significant time and means your experiment benefits from code that has already been tested on live animals.

If no existing protocol fits, decide how much to build from scratch:

  - If your experiment is a two-alternative choice task (two stimuli, two response ports, rewarded for correct choice), inherit from TwoAltChoiceExp and override specific methods. Most protocols in glab\_behaviors follow this pattern.

  - If your experiment has a fundamentally different structure (go/no-go, free operant, autoshaping), inherit from BaseExp and implement the trial loop yourself.

See Chapter 8 for a full description of the protocols available in glab\_behaviors.

### 10.2 Experiment Structure

|               |                                                                                              |
| ------------- | -------------------------------------------------------------------------------------------- |
| **Method**    | **Purpose**                                                                                  |
| \_\_init\_\_  | Accept experiment parameters (stimuli, durations, etc.) and store them as attributes.        |
| session\_pre  | Called once at the start of a session. Initialize counters, log start time, reset the panel. |
| session\_main | The main trial loop. Called repeatedly until the session ends. Returns the next state name.  |
| run\_trial    | Logic for a single trial: present stimulus, wait for response, deliver consequence.          |
| session\_post | Called once at the end. Save data, reset the panel, send summary email if configured.        |

### 10.3 A Complete Example

File: go\_nogo.py

```
import datetime, random, logging
from pyoperant.behavior.base import BaseExp
from pyoperant import utils
logger = logging.getLogger(__name__)
class GoNogo(BaseExp):
def __init__(self, panel, subject, go_stims, nogo_stims,
reward_dur=2.0, timeout_dur=10.0, **kwargs):
super(GoNogo, self).__init__(panel=panel, subject=subject, **kwargs)
self.go_stims = go_stims
self.nogo_stims = nogo_stims
self.reward_dur = reward_dur
self.timeout_dur = timeout_dur
self.trials = []
def session_pre(self):
self.session_start = datetime.datetime.now()
self.panel.reset()
self.panel.house_light.on()
return 'main'
def session_main(self):
if self._check_session_end():
return 'post'
self.run_trial()
return 'main'
def run_trial(self):
is_go = random.random() > 0.5
wav = random.choice(self.go_stims if is_go else self.nogo_stims)
self.panel.center.on()
peck_time = self.panel.center.poll()
self.panel.center.off()
self.panel.speaker.queue(wav)
self.panel.speaker.play()
response = self.panel.center.poll(timeout=3.0)
if is_go and response is not None:
self.panel.hopper.feed(dur=self.reward_dur)
outcome = 'hit'
elif not is_go and response is None:
outcome = 'correct_rejection'
elif is_go and response is None:
outcome = 'miss'
else:
self.panel.house_light.timeout(dur=self.timeout_dur)
outcome = 'false_alarm'
self.trials.append({'time': peck_time, 'stimulus': wav,
'is_go': is_go, 'outcome': outcome})
logger.info('Trial outcome: %s' % outcome)
def session_post(self):
self.panel.reset()
logger.info('Session complete. %d trials run.' % len(self.trials))
self._save_data()
def _check_session_end(self):
elapsed = datetime.datetime.now() - self.session_start
return elapsed.total_seconds() > 7200
def _save_data(self):
import csv, os
outfile = os.path.join(self.parameters['experiment_path'], 'trials.csv')
with open(outfile, 'wb') as f:
writer = csv.DictWriter(f, fieldnames=self.trials[0].keys())
writer.writeheader()
writer.writerows(self.trials)
```

### 10.4 Running the Experiment

Once your behavior script and config.json are in place, run the experiment from the command line using the behave entry point:

```
behave GoNogo -P 1 -S bird42 -c config.json
```

The arguments are:

  - \-P / --panel: the panel identifier (must match a key in the PANELS dict in your local config)

  - \-S / --subject: the subject identifier (used for the data directory and log file names)

  - \-c / --config: path to the config.json file (default: config.json in the current directory)

See Section 10.5 for a full description of the config.json file and all available parameters.

### 10.5 The config.json File

Every experiment is configured by a JSON file — typically named config.json and stored in the subject’s data directory. When you run behave, it reads this file and passes all of its key-value pairs as keyword arguments to the behavior class constructor. Any key in the JSON becomes a key in self.parameters inside the behavior.

The file is written once per subject (or once per experimental condition change) and lives alongside the data it produces:

```
/home/pi/opdat/B1234/config.json
/home/pi/opdat/B1234/B1234.log
/home/pi/opdat/B1234/B1234_trialdata_20260401120000.csv
```

#### Parameters Accepted by All Experiments (BaseExp)

These keys are read by BaseExp and apply regardless of which behavior class you use:

|                      |                 |                         |                                                                                                                                                                      |
| -------------------- | --------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Key**              | **Type**        | **Default**             | **Description**                                                                                                                                                      |
| subject              | string          | required                | Subject identifier. Used for log file and data file names.                                                                                                           |
| panel\_name          | string          | required                | Panel identifier. Must match a key in the PANELS dict in your local config.                                                                                          |
| experiment\_path     | string          | required                | Absolute path to the subject’s data directory. Must exist before starting.                                                                                           |
| stim\_path           | string          | experiment\_path/stims  | Absolute path to the directory containing stimulus wav files.                                                                                                        |
| experimenter         | object          | omit                    | Experimenter info. Contains 'name' (string) and 'email' (string). The email address is used when log\_handlers includes 'email'.                                     |
| light\_schedule      | string or list  | 'sun'                   | When the house lights should be on. 'sun' uses local sunrise/sunset in La Jolla. Or a list of \[start, end\] pairs in 'HH:MM' format, e.g. \[\["06:00", "20:00"\]\]. |
| session\_schedule    | string or list  | same as light\_schedule | When sessions should run. Same format as light\_schedule. Defaults to light\_schedule if omitted.                                                                    |
| idle\_poll\_interval | float           | 60.0                    | Seconds to wait between checks when the experiment is idle.                                                                                                          |
| shape                | string or false | false                   | Set to 'block1' through 'block5' to run that shaping block before the main session loop. Set to false or omit to skip shaping.                                       |
| log\_handlers        | list            | \[\]                    | Additional log handlers. Pass \["email"\] to enable email notifications on warnings. Requires experimenter.email to be set.                                          |
| free\_food\_schedule | list            | omit to disable         | Time windows during which free food is delivered between sessions. Same format as light\_schedule.                                                                   |
| name                 | string          | ''                      | Human-readable name for the experiment. Saved in the snapshot JSON; not used by the code.                                                                            |
| description          | string          | ''                      | Human-readable description. Saved in the snapshot JSON; not used by the code.                                                                                        |
| debug                | bool            | false                   | If true, sets log level to DEBUG for more verbose output.                                                                                                            |

#### Parameters for TwoAltChoiceExp

These additional keys are read by TwoAltChoiceExp. They must be present in config.json when running a two-alternative choice task:

|                                  |          |                     |                                                                                                                             |
| -------------------------------- | -------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Key**                          | **Type** | **Required**        | **Description**                                                                                                             |
| classes                          | object   | yes                 | Defines the stimulus classes. See Classes below.                                                                            |
| stims                            | object   | yes                 | Maps stimulus names to wav filenames relative to stim\_path. e.g. {"stim\_a": "a.wav", "stim\_b": "b.wav"}.                 |
| response\_win                    | float    | yes                 | Seconds after stimulus onset to wait for a response before marking the trial as no-response.                                |
| intertrial\_min                  | float    | yes                 | Minimum seconds to wait between trials.                                                                                     |
| correction\_trials               | bool     | yes                 | If true, repeat the same stimulus after an incorrect response until the subject responds correctly.                         |
| no\_response\_correction\_trials | bool     | false               | If true, also run correction trials after no-response trials. Only used when correction\_trials is true.                    |
| reinforcement                    | object   | omit for continuous | Reinforcement schedule. See Reinforcement below. Omit for continuous reinforcement.                                         |
| block\_design                    | object   | omit for random     | Controls trial ordering. See Block Design below. Omit to use random sampling across all classes.                            |
| add\_fields\_to\_save            | list     | omit                | Additional trial fields to include in the CSV output beyond the defaults.                                                   |
| cue\_duration                    | float    | omit                | If present, a cue light is shown for this many seconds before each stimulus. Requires a 'cue' key in each class definition. |
| cuetostim\_wait                  | float    | omit                | Seconds to wait between cue offset and stimulus onset. Only used when cue\_duration is set.                                 |

#### The classes Object

The classes object defines each stimulus class — what response is correct, what the reward and punishment durations are, and optionally what cue light to show. Each key is a class name; the value is an object with the following fields:

|               |              |                                                                                                                             |
| ------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| **Field**     | **Required** | **Description**                                                                                                             |
| component     | yes          | The name of the response port that is correct for this class. Must match a panel attribute, e.g. 'left' or 'right'.         |
| reward\_value | yes          | Duration of the hopper feed in seconds for a correct response.                                                              |
| punish\_value | yes          | Duration of the house light timeout in seconds for an incorrect response.                                                   |
| cue           | no           | Cue light color to show before this stimulus: 'red', 'green', or 'blue'. Only used when cue\_duration is set in the config. |

#### The reinforcement Object

Controls partial reinforcement schedules for correct responses. Incorrect responses are always punished regardless of schedule. Omit this key entirely for continuous reinforcement (every correct response rewarded).

|                    |                       |                                                                                                                                     |
| ------------------ | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **schedule value** | **Additional fields** | **Description**                                                                                                                     |
| 'continuous'       | none                  | Every correct response is rewarded. This is the default if reinforcement is omitted.                                                |
| 'fixed\_ratio'     | ratio (int)           | Reward after every nth correct response. e.g. ratio: 3 rewards every 3rd correct response.                                          |
| 'variable\_ratio'  | ratio (int)           | Reward after a random number of correct responses averaging n. The threshold is resampled from \[1, 2\*ratio-1\] after each reward. |
| 'percent\_reinf'   | prob (float 0–1)      | Reward each correct response with this probability. e.g. prob: 0.5 rewards 50% of correct responses.                                |

All schedules also accept an optional secondary field (bool). If true, a brief center port flash is given as secondary reinforcement on correct trials before the hopper is raised.

#### The block\_design Object

Controls how trials are ordered across sessions. If omitted, all stimulus classes are sampled randomly with equal probability up to 100 trials. The block\_design object has two keys:

  - blocks — a dict of named blocks. Each block has a 'queue' type ('random', 'block', or 'mixedDblStaircase') and a 'conditions' list. For 'random' and 'block' queues, each condition is a dict with at least a 'class' key (matching a key in classes) and a 'stim\_name' key (matching a key in stims).

  - order — a list of block names defining the session sequence. The experiment cycles through these in order.

#### A Complete Example

Below is a complete config.json for a two-alternative choice auditory discrimination task, matching the style of the example configs in the py-behaviors repository:

```
{
"experimenter": {
"name": "Your Name",
"email": "yourname@ucsd.edu"
},
"subject": "B1234",
"panel_name": "1",
"experiment_path": "/home/pi/opdat/B1234",
"stim_path": "/home/pi/opdat/B1234/stimuli",
"name": "Starling vs Finch discrimination",
"description": "Two-alternative choice, v1",
"debug": false,
"log_handlers": ["email"],
"light_schedule": "sun",
"response_win": 5.0,
"intertrial_min": 5.0,
"correction_trials": true,
"shape": false,
"stims": {
"starling": "starling.wav",
"finch": "finch.wav"
},
"classes": {
"L": {"component": "left", "reward_value": 2.0, "punish_value": 5.0},
"R": {"component": "right", "reward_value": 2.0, "punish_value": 5.0}
},
"block_design": {
"blocks": {
"default": {
"queue": "random",
"conditions": [
{"class": "L", "stim_name": "starling"},
{"class": "R", "stim_name": "finch"}
]
}
},
"order": ["default"]
},
"reinforcement": {
"schedule": "percent_reinf",
"prob": 0.5,
"secondary": true
}
}
```

When behave loads this file, every key becomes available inside the behavior class as self.parameters\['key'\]. The subject, panel\_name, and experiment\_path keys are consumed by BaseExp directly and do not need to be passed on the command line if they are present in the config file.

## 11. Analyzing Behavioral Data

This chapter describes the data files produced by PyOperant, the two analysis codebases available for working with those files, and how to use them in practice. Analysis is typically done on the MagPi server or on your own analysis machine — not on the MagPi clients themselves.

### 11.1 Data Files Produced by PyOperant

Each experiment produces several files, all written to the bird’s experiment directory (/home/pi/opdat/BXXXX/ on the MagPi client, mirrored to the server by rsync):

#### Trial Data CSV

The primary data file. For TwoAltChoiceExp, a new CSV is created at the start of each run of the behave script, named:

```
BXXXX_trialdata_YYYYMMDDHHMMSS.csv
```

Each row is one trial. The default columns are:

|            |            |                                                          |
| ---------- | ---------- | -------------------------------------------------------- |
| **Column** | **Type**   | **Description**                                          |
| session    | int        | Session index within this run of the experiment          |
| index      | int        | Trial index (increments continuously across sessions)    |
| type\_     | str        | 'normal' or 'correction'                                 |
| stimulus   | str        | Full path to the wav file played on this trial           |
| class\_    | str        | Stimulus class (e.g. 'L' or 'R')                         |
| response   | str        | Port the bird pecked ('left', 'right'), or 'none'        |
| correct    | bool/None  | True if correct, False if incorrect, None if no response |
| rt         | float/None | Reaction time in seconds from stimulus onset, or None    |
| reward     | bool/str   | True if reward delivered; 'error' if hopper failed       |
| punish     | bool       | True if timeout was delivered                            |
| time       | datetime   | Timestamp of the trial initiation peck                   |

Additional columns can be added via add\_fields\_to\_save in the config. Because a new CSV is created each time behave is started, a bird running across many days will accumulate multiple files with different timestamps. Load and concatenate all of them for a full history.

#### Summary DAT

A plain-text file updated at the end of each session, named BXXXX.summaryDAT. It contains counts of trials, feeds, and hopper failures for the current session. This is what the server’s all.summary aggregation script reads. Useful for a quick status check but does not contain trial-by-trial data.

#### Log File

A per-bird log file (BXXXX.log) in CSV format with columns timestamp, level, and message. Most useful for debugging hardware errors or unexpected session behavior.

#### Persistent Queue State

If the experiment uses an adaptive staircase, the queue state is pickled to persistentQ.pkl in the bird’s experiment directory. This is loaded automatically on the next session to resume the staircase. Delete this file to reset the staircase when starting a new experimental phase.

### 11.2 Analysis Codebases Overview

The lab maintains two separate analysis codebases that complement each other:

|                    |                                    |                                                                                                             |
| ------------------ | ---------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Package**        | **Location**                       | **Purpose**                                                                                                 |
| pyoperant.analysis | pyoperant/analysis.py              | Low-level psychophysical metrics (d-prime, accuracy, MCC) computed from confusion matrices.                 |
| behav              | gentnerlab/behav-analysis (GitHub) | Higher-level data loading, filtering, and visualization tools. The primary package for day-to-day analysis. |

In practice, most analysis workflows use behav for loading and plotting, and optionally drop down to pyoperant.analysis for specific psychophysical metrics.

### 11.3 The pyoperant.analysis Module

The pyoperant.analysis module (pyoperant/analysis.py) provides functions for computing standard psychophysical metrics from a confusion matrix. All functions operate on numpy arrays.

#### Building a Confusion Matrix

```
from pyoperant.analysis import create_conf_matrix, Performance
import numpy as np
expected = np.array([0, 0, 1, 1, 0, 1]) # true class indices
predicted = np.array([0, 1, 1, 0, 0, 1]) # bird's response indices
cm = create_conf_matrix(expected, predicted)
# cm[i, j] = number of trials where true class was i, response was j
```

#### The Performance Class

```
perf = Performance(expected, predicted)
perf.acc() # fraction correct
perf.acc_ci() # 95% confidence interval (beta distribution)
perf.dprime() # d-prime (2-class tasks only)
perf.mcc() # Matthews correlation coefficient (2-class tasks only)
```
> *dprime() and mcc() return False if the confusion matrix has more than two classes. For tasks with more than two alternatives, use acc() only.*

#### Standalone Functions

```
from pyoperant.analysis import dprime, acc, acc_ci, mcc
dp = dprime(cm) # d-prime
a = acc(cm) # fraction correct
ci = acc_ci(cm) # (lower, upper) confidence interval
m = mcc(cm) # Matthews correlation coefficient
```

### 11.4 The behav-analysis Package

The behav-analysis package (github.com/gentnerlab/behav-analysis) is the primary tool for loading and visualising PyOperant data. It is written by Marvin Thielk and is compatible with Python 2 and 3 via the six library.

Install it on your analysis machine:

```
git clone https://github.com/gentnerlab/behav-analysis.git
cd behav-analysis
pip install -r requirements.txt
pip install -e .
```

The package has three modules:

|                |                                                                                                                              |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Module**     | **Description**                                                                                                              |
| behav.loading  | Loads data from multiple file formats into a unified dict of pandas DataFrames, one per subject.                             |
| behav.utils    | Filtering helpers, confidence intervals, p-value formatting, and stimulus name extraction.                                   |
| behav.plotting | Visualization functions: performance calendars, per-stimulus accuracy heatmaps, accuracy/bias traces, and trial/feed counts. |

#### behav.loading

The central function is load\_data\_pandas(), which loads all data files for a list of subjects and returns a dict mapping subject ID to a pandas DataFrame with a datetime index:

```
from behav import loading
subjects = ('B1178', 'B1186', 'B1049')
data_path = '/mnt/cube/RawData/Zog/' # top-level data folder
behav_data = loading.load_data_pandas(subjects, data_path)
# behav_data['B1178'] is a DataFrame with all trials for B1178
```

The function handles three file formats automatically, detecting which is present by filename pattern:

  - PyOperant CSV files (BXXXX\_trialdata\_\*.csv) — the format produced by the current MagPi system

  - Legacy rDAT files (\*\_match2sample\*.2ac\_rDAT) — from older C-based operant scripts

  - AllTrials files (BXXXX.AllTrials) — from probe-the-broab

All formats are normalized to the same column names (session, type\_, stimulus, class\_, response, correct, reward, time) so downstream code works identically regardless of source. The reward column is coerced to boolean by default.

If data files are not found for a subject, a warning is printed and that subject is omitted from the returned dict.

#### behav.utils

The utils module provides several frequently-needed helpers:

filter\_normal\_trials(df) — the most commonly used filter. Removes correction trials and no-response trials, leaving only normal trials where the bird made a response. Call this before any performance calculation:

```
from behav import utils
df_clean = utils.filter_normal_trials(behav_data['B1178'])
```

filter\_recent\_days(df, num\_days) — slices the DataFrame to the most recent num\_days of data relative to today:

```
df_recent = utils.filter_recent_days(behav_data['B1178'], num_days=7)
```

extract\_filename(df, target='stim\_name') — parses the full stimulus path in the stimulus column and adds a new column containing just the filename without extension. Useful for grouping trials by stimulus identity rather than full path:

```
utils.extract_filename(df_clean) # adds 'stim_name' column in-place
```

binomial\_ci(x, N, CL=95.0) — exact binomial confidence interval (Clopper-Pearson). Returns (lower, upper) bounds. Handles edge cases (x=0 or x=N) correctly:

```
lower, upper = utils.binomial_ci(73, 100) # 73 correct out of 100 trials
```

stars(p) — converts a p-value to an R-style significance string ('\*\*\*', '\*\*', '\*', '.', 'n.s.'):

```
utils.stars(0.003) # returns '**'
```

#### behav.plotting

All plotting functions use matplotlib and seaborn and return the figure object so it can be saved or further modified. The standard analysis workflow from the lab notebook is:

```
import matplotlib.pyplot as plt
from behav import plotting, utils, loading
import seaborn as sns
subjects = ('B1178', 'B1186')
behav_data = loading.load_data_pandas(subjects, '/mnt/cube/RawData/Zog/')
for subj, data in behav_data.items():
plotting.plot_filtered_performance_calendar(subj, data, num_days=20)
plotting.plot_ci_accuracy(subj, data)
plotting.plot_daily_accuracy(subj, data, x_axis='trial_num')
plotting.plot_trial_feeds(behav_data)
plt.show()
```

The individual plotting functions are:

|                                                              |                                                                                                                                                                                                                                       |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Function**                                                 | **Description**                                                                                                                                                                                                                       |
| plot\_performance\_calendar(subj, df)                        | Three-panel heatmap (date × hour) showing trial counts, accuracy, and feed counts. One column per day, one row per hour.                                                                                                              |
| plot\_filtered\_performance\_calendar(subj, df, num\_days=7) | Convenience wrapper: applies filter\_normal\_trials and filter\_recent\_days before calling plot\_performance\_calendar.                                                                                                              |
| plot\_accperstim(title, df)                                  | Heatmap of accuracy broken down by stimulus and day. Stimulus names are extracted from full paths automatically. Useful for identifying which stimuli a bird is struggling with.                                                      |
| plot\_filtered\_accperstim(title, df, num\_days=7)           | Convenience wrapper: applies filters before calling plot\_accperstim.                                                                                                                                                                 |
| plot\_accuracy\_bias(subj, df)                               | Full-featured accuracy/bias trace. Configurable x-axis (time or trial number), smoothing method (exponential, rolling, gaussian), and which series to display (accuracy, L-bias, R-bias). Includes optional confidence interval band. |
| plot\_daily\_accuracy(subj, df)                              | Preset of plot\_accuracy\_bias: shows today’s trials only, gaussian smoothing, accuracy only, x-axis by trial number.                                                                                                                 |
| plot\_ci\_accuracy(subj, df, day\_lim=7)                     | Preset of plot\_accuracy\_bias: rolling mean with confidence interval band, x-axis by time, last 7 days.                                                                                                                              |
| plot\_trial\_feeds(behav\_data, num\_days=7)                 | Multi-bird summary: trials per day and feeds per day for all subjects on one figure, with color-coded lines. Takes the full behav\_data dict, not a single DataFrame.                                                                 |

### 11.5 Complete Analysis Workflow Example

The following is a complete example combining both packages, matching the pattern used in the lab’s analysis notebook:

```
import numpy as np
import matplotlib.pyplot as plt
from behav import loading, utils, plotting
from pyoperant.analysis import Performance
# 1. Load data
subjects = ('B1178', 'B1186')
behav_data = loading.load_data_pandas(subjects, '/mnt/cube/RawData/Zog/')
# 2. Plot recent overview for each bird
for subj, df in behav_data.items():
plotting.plot_filtered_performance_calendar(subj, df, num_days=14)
plotting.plot_ci_accuracy(subj, df, day_lim=14)
# 3. Compute summary metrics for each bird
class_map = {'L': 0, 'R': 1}
resp_map = {'left': 0, 'right': 1, 'L': 0, 'R': 1}
for subj, df in behav_data.items():
df_clean = utils.filter_normal_trials(utils.filter_recent_days(df, 7))
expected = df_clean['class_'].map(class_map).dropna().astype(int)
predicted = df_clean['response'].map(resp_map).dropna().astype(int)
idx = expected.index.intersection(predicted.index)
perf = Performance(expected[idx].values, predicted[idx].values)
print('%s n=%d acc=%.2f d-prime=%.2f' % (
subj, len(idx), perf.acc(), perf.dprime()))
# 4. Multi-bird trial/feed summary
plotting.plot_trial_feeds(behav_data, num_days=14)
plt.show()
```

### 11.6 Limitations and Further Analysis

The behav-analysis package covers the most common daily monitoring and reporting tasks. For more specialized analyzes — psychometric curve fitting, reaction time distributions, inter-session learning curves, or multi-bird statistical comparisons — the recommended approach is to build on top of the DataFrames that load\_data\_pandas() returns, using standard Python scientific libraries (scipy, statsmodels, matplotlib) in a Jupyter notebook.

A few practical notes:

  - filter\_normal\_trials() must be called before any performance calculation. Correction trials are not independent and will inflate apparent accuracy if included.

  - The reward column is coerced to boolean by load\_data\_pandas(). The string 'error' (produced when the hopper fails) is mapped to False. Filter to reward == True when computing feed counts.

  - response values may be 'left'/'right' (PyOperant CSV) or 'L'/'R' (rDAT). The plotting functions handle both, but if you are constructing a confusion matrix manually use a mapping that covers both conventions.

  - The time column is the MagPi client’s system clock, synchronized via NTP on boot. Small drifts between reboots are possible. Always verify that date ranges look sensible before pooling data across days.

  - Multiple CSV files for the same bird are concatenated and sorted by time index by load\_data\_pandas(). The session column resets to 0 at each restart, so use the time index rather than session number to order trials chronologically across files.

## 12. Quick Reference

### 12.1 Key Files

|                                            |                                                                                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **File**                                   | **Purpose**                                                                                                                          |
| pyoperant/local.py                         | Routes to correct local config: hostname for zog/vogel; /etc/magpi\_revision for MagPi clients.                                      |
| pyoperant/local\_pi\_revd.py               | Hardware configuration for Rev D MagPi clients (servo hopper, second PCA9685).                                                       |
| pyoperant/local\_pi\_revc.py               | Hardware configuration for Rev C MagPi clients (solenoid hopper, GPIO 16).                                                           |
| pyoperant/components.py                    | Component classes: Hopper, PeckPort, HouseLight, etc.                                                                                |
| pyoperant/hwio.py                          | Hardware IO abstraction: BooleanInput, BooleanOutput, PWMOutput.                                                                     |
| pyoperant/interfaces/raspi\_gpio\_.py      | Raspberry Pi / PCA9685 hardware interface.                                                                                           |
| pyoperant/behavior/base.py                 | Base behavior class (BaseExp) and the state machine runner.                                                                          |
| pyoperant/behavior/two\_alt\_choice.py     | Built-in two-alternative choice behavior (TwoAltChoiceExp).                                                                          |
| pyoperant/behavior/shape.py                | Shaping protocols (Shaper, Shaper2AC, ShaperGoNogo, etc.).                                                                           |
| scripts/behave                             | Command-line entry point for running experiments.                                                                                    |
| scripts/tune\_servo.py                     | Interactive servo angle tuning script for Rev D panels (angles in degrees). Run on the MagPi client before first use of a new panel. |
| scripts/test\_panel.py                     | Standalone script to run the full panel component test. Auto-detects board revision from /etc/magpi\_revision.                       |
| pyoperant/analysis.py                      | Psychophysical metrics: d-prime, accuracy, MCC, confusion matrix.                                                                    |
| glab\_behaviors/\_\_init\_\_.py            | Exports all protocols from the py-behaviors repo — add new protocol imports here.                                                    |
| glab\_behaviors/Basic\_2AC.py              | Standard two-alternative choice protocol — good starting point for new experiments.                                                  |
| glab\_behaviors/SameDifProbs.py            | Same/different discrimination with probabilistic stimulus presentation.                                                              |
| glab\_behaviors/EvidenceAccumExperiment.py | Evidence accumulation task with Markovian block structure.                                                                           |
| behav/loading.py                           | Multi-format data loader (PyOperant CSV, rDAT, AllTrials) — behav-analysis repo.                                                     |
| behav/utils.py                             | Filtering helpers, confidence intervals, p-value formatting — behav-analysis repo.                                                   |
| behav/plotting.py                          | Performance calendars, accuracy traces, per-stimulus heatmaps — behav-analysis repo.                                                 |

### 12.2 Useful Commands

|                              |                                                                       |
| ---------------------------- | --------------------------------------------------------------------- |
| **Command**                  | **Purpose**                                                           |
| sudo pigpiod                 | Start the pigpio daemon (required before running any experiment).     |
| i2cdetect -y 1               | List all I2C devices on bus 1. Expect 0x55 (lights) and 0x45 (servo). |
| behave GoNogo -P 1 -S bird42 | Run the GoNogo protocol on panel 1 for subject bird42.                |
| tail -f logfile.log          | Follow a log file in real time during a running session.              |
| git pull                     | Update PyOperant from the GitHub repository.                          |
| pip install -e .             | Reinstall PyOperant in editable mode after pulling changes.           |

### 12.3 Getting Help

  - Check the log file for the full error traceback.

  - Search the open issues on the PyOperant GitHub repository: github.com/gentnerlab/pyoperant/issues

  - Ask a more senior lab member.

  - Read the PyOperant documentation: pyoperant.readthedocs.org

## Appendix A: Fabrication Details and Bill of Materials

This appendix provides the information needed to order parts and have the RPiOperant Rev D interface board fabricated and assembled. It covers PCB fabrication specifications, assembly notes, and the complete bill of materials (BOM). The 2026 production run of 30 boards was fabricated by Bittele Electronics (7pcb.com).

### A.1 PCB Fabrication Specifications

The following specifications apply to the RPiOperant interface board (PCBA-000001 Rev D). Submit the Gerber and drill files from the hardware repository to any IPC Class 2 capable PCB fabricator. These specifications match what was used for the 2026 Bittele run.

|                             |                                          |
| --------------------------- | ---------------------------------------- |
| **Parameter**               | **Value**                                |
| Board thickness             | 1.6 mm                                   |
| Layer count                 | 4                                        |
| Copper weight, outer layers | 1 oz (35 µm)                             |
| Copper weight, inner layers | 0.5 oz (17.5 µm)                         |
| Minimum trace / space       | 0.1 mm / 0.1 mm                          |
| Minimum finished drill      | 0.2 mm                                   |
| Surface finish              | ENIG (Electroless Nickel Immersion Gold) |
| Solder mask                 | Green LPI, both sides                    |
| Silkscreen                  | White, top side                          |
| IPC class                   | Class 2                                  |
| Controlled impedance        | Not required                             |
| Edge connector bevel        | Not required                             |

> *Note: The Gerber files, drill files, assembly drawing, and centroid/CPL file will be published at github.com/gentnerlab/rpioperant-hardware. Contact the lab manager if the repository is not yet available.*

### A.2 Assembly Notes

All SMD components are on the top side of the board. Through-hole connectors are on the bottom side. The following components require particular care during assembly:

PCA9685 (U1, U7): TSSOP-28 package with 0.65 mm pitch. Inspect for solder bridges under magnification after reflow. Verify orientation against the assembly drawing before soldering.

TPSM64404RCHR (U4): This power module has an exposed pad on the underside that must be soldered to the board thermal pad for proper heat dissipation. Use sufficient solder paste on the thermal pad and confirm reflow temperature profile matches the datasheet.

GPIO pass-through connector (J1, PPPC202LFBN-RC): This 2x20 female socket mounts on the top side and must be pressed fully flush before soldering. Its height sets the spacing between the RPiOperant board and the Raspberry Pi below; use only the specified 11 mm M3 standoffs to maintain correct clearance.

The HiFiBerry Amp2 and Raspberry Pi 3B+ are not soldered to the board. They connect via GPIO headers and are secured with M3 standoffs and screws. Do not substitute standoffs of a different height.

### A.3 Bill of Materials

Quantities are per board. Digikey part numbers are from the 2026 order; verify availability before placing a new order as part numbers and stock levels change. Items marked — for Digikey part number are sourced directly from the manufacturer website.

|                                                   |         |                      |                           |
| ------------------------------------------------- | ------- | -------------------- | ------------------------- |
| **Description**                                   | **Qty** | **Mfr Part No.**     | **Digikey Part No.**      |
| Capacitor, radial, 220 µF 50 V                    | 1       | 50TZV220M10X10.5     | 1189-1654-1-ND            |
| Capacitor, 1206, 10 µF 50 V                       | 7       | CL31B106KBHNNNE      | 1276-6767-1-ND            |
| Capacitor, 0805, 0.1 µF 100 V                     | 8       | 08051C104JAT2A       | 478-KGM21AR72A104JUCT-ND  |
| Capacitor, 0805, 1.0 µF 50 V                      | 2       | GRM21BR71H105KA12L   | 490-4736-1-ND             |
| Capacitor, 0805, 0.1 µF 50 V (alt.)               | 2       | CC0805KRX7R9BB104    | 311-1140-1-ND             |
| Capacitor, 1206, 47 µF 25 V                       | 2       | C3216X5R1E476M160AC  | 445-8047-1-ND             |
| Capacitor, 0805, 22 µF 25 V                       | 3       | GRT21BR61E226ME13L   | 490-12389-1-ND            |
| Capacitor, 0603, 10 pF 50 V                       | 1       | C0603C100J5GACTU     | 399-C0603C100J5GACTUCT-ND |
| Capacitor, 0603, 5.0 pF 250 V                     | 1       | CBR06C509BAGAC       | 399-8735-1-ND             |
| IC, Hex Schmitt-Trigger Inverter (SN74LVC14A)     | 2       | SN74LVC14AQDRQ1      | 296-SN74LVC14AQDRQ1CT-ND  |
| IC, 16-ch PWM Controller (PCA9685PW)              | 2       | PCA9685PW,118        | 568-11925-1-ND            |
| IC, DC/DC Power Module (TPSM64404RCHR)            | 1       | TPSM64404RCHR        | 296-TPSM64404RCHRCT-ND    |
| IC, LDO Regulator (TPS7A2633DRVR)                 | 1       | TPS7A2633DRVR        | 296-TPS7A2633DRVRCT-ND    |
| IC, Octal Level Shifter (SN74LVC4245APWR)         | 1       | SN74LVC4245APWR      | 296-12183-1-ND            |
| IC, Voltage Supervisor 2.9 V (APX803L40-29SA-7)   | 1       | APX803L40-29SA-7     | 31-APX803L40-29SA-7CT-ND  |
| IC, Voltage Supervisor 4.5 V (APX803L40-45SA-7)   | 1       | APX803L40-45SA-7     | 31-APX803L40-45SA-7CT-ND  |
| MOSFET, N-ch, house light driver (SQ2364EES)      | 5       | SQ2364EES-T1\_BE3    | 2N7002LT1GOSCT-ND         |
| Resistor, 0805, 4.32 kΩ 1%                        | 14      | ERJ-6ENF4321V        | P4.32KCCT-ND              |
| Resistor, 0805, 100 Ω 1%                          | 3       | ERJ-6ENF1000V        | P100CCT-ND                |
| Resistor, 0805, 332 Ω 1%                          | 11      | ERJ-6ENF3320V        | P332CCT-ND                |
| Resistor, 0805, 107 kΩ 1%                         | 1       | ERJ-6ENF1073V        | P107KCCT-ND               |
| Resistor, 0805, 681 Ω 1%                          | 2       | ERJ-6ENF6810V        | P681CCT-ND                |
| Resistor, 0805, 9.31 kΩ 1%                        | 1       | ERJ-6ENF9311V        | P9.31KCCT-ND              |
| Resistor, 0805, 10.0 kΩ 1%                        | 3       | ERJ-6ENF1002V        | P10.0KCCT-ND              |
| Resistor, 0805, 140 kΩ 1%                         | 1       | ERJ-6ENF1403V        | P140KCCT-ND               |
| Resistor, 0805, 64.9 kΩ 1%                        | 1       | ERJ-6ENF6492V        | P64.9KCCT-ND              |
| Resistor, 0805, 8.45 kΩ 1%                        | 1       | ERJ-6ENF8451V        | P8.45KCCT-ND              |
| Resistor, 0805, 121 Ω 1%                          | 1       | ERJ-6ENF1210V        | P121CCT-ND                |
| Resistor, 0805, 0 Ω jumper                        | 2       | ERJ-6GEY0R00V        | P0.0ACT-ND                |
| Trimmer potentiometer, 10 kΩ                      | 2       | 3362U-1-103LF        | 3362U-103LF-ND            |
| Ferrite bead, 600 Ω @ 100 MHz                     | 1       | HI2220P601R-10       | 240-2427-1-ND             |
| Connector, Molex KK 254, 2-pin housing            | 2       | 0022-23-2021         | 900-0022232021-ND         |
| Connector, Molex KK 254, 3-pin housing            | 1       | 0022-23-2031         | WM4201-ND                 |
| Connector, Molex KK 254, 4-pin housing            | 1       | 0022-23-2041         | WM4202-ND                 |
| Connector, Molex KK 254, 6-pin housing            | 1       | 0022-23-2061         | WM4204-ND                 |
| Connector, Molex Micro-Fit 3.0, 4-pin             | 1       | 61400416021          | 732-2106-ND               |
| Connector, IDC, 50-pin (0.1" pitch)               | 2       | 10029449-111RLF      | 609-4614-1-ND             |
| Connector, pin header, 5x1, 0.1" pitch            | 2       | TSW-105-07-T-S       | SAM1035-05-ND             |
| Connector, D-Sub DE-25 male, PCB mount            | 1       | SBH11-PBPC-D25-ST-BK | S9176-ND                  |
| Connector, 2x20 female socket (GPIO pass-through) | 1       | PPPC202LFBN-RC       | S7123-ND                  |
| Connector, audio jack, 3.5 mm, 3-pos              | 1       | 090131-0780          | WM8152-ND                 |
| Standoff, M3.0 x 0.5 mm, 11 mm, steel             | 8       | 9774110360R          | 732-5278-1-ND             |
| Screw, M3.0 x 0.5 x 5 mm, SS, Phillips pan head   | 8       | 6829                 | —                         |
| Module, HiFiBerry Amp2 v1.0                       | 1       | —                    | hifiberry.com             |
| Module, Raspberry Pi 3 Model B+                   | 1       | —                    | Approved distributor      |
| Servo, GoBilda 25-2 Torque (hopper actuator)      | 1       | 2000-0025-0002       | gobilda.com               |

### A.4 Board Bring-Up Procedure

After assembly, perform these checks before connecting a Raspberry Pi for the first time:

1\. Visual inspection: examine the PCA9685 TSSOP packages and TPSM64404RCHR power module pads for solder bridges. Check all SMD components for correct placement and orientation against the assembly drawing.

2\. Power rail verification (Raspberry Pi disconnected): apply 12 V to the main input. Measure the following rails at the designated test points and confirm all are within ±5% of nominal: +12 V regulated (house light rail), +6 V (servo rail), +5 V (RPi power), +3.3 V.

3\. I2C check (Raspberry Pi connected): run i2cdetect -y 1. Two addresses must respond: 0x55 (lights PCA9685, U1) and 0x45 (servo PCA9685, U7). If an address is absent, re-inspect the solder joints on that chip and verify the A0–A5 address pin resistors.

4\. Full panel test: run python3 scripts/test\_panel.py as described in Section 6.5. Each component should pass before the board is placed into service.

## Appendix B: Component Reference Specifications

This appendix summarizes the key specifications for the three principal components of the MagPi client electronics. For full datasheets, refer to the manufacturer links below.

### B.1 Raspberry Pi 3 Model B+

The Raspberry Pi 3 Model B+ is the single-board computer at the heart of each MagPi client. It was released on 14 March 2018 and is the final revision of the Raspberry Pi 3 family.

Official datasheet: datasheets.raspberrypi.com/rpi3/raspberry-pi-3-b-plus-product-brief.pdf

|                       |                                                                               |
| --------------------- | ----------------------------------------------------------------------------- |
| **Parameter**         | **Value**                                                                     |
| SoC                   | Broadcom BCM2837B0                                                            |
| CPU                   | Quad-core ARM Cortex-A53 (ARMv8) 64-bit @ 1.4 GHz                             |
| RAM                   | 1 GB LPDDR2 SDRAM                                                             |
| Wireless LAN          | Dual-band 2.4 GHz / 5 GHz IEEE 802.11b/g/n/ac (Cypress CYW43455)              |
| Bluetooth             | Bluetooth 4.2 / BLE                                                           |
| Ethernet              | Gigabit Ethernet over USB 2.0 via Microchip LAN7515 (max throughput 300 Mbps) |
| USB                   | 4 × USB 2.0                                                                   |
| GPIO                  | 40-pin header (BCM numbering used throughout codebase)                        |
| I2C                   | 2 × I2C buses (bus 1: SDA = GPIO2, SCL = GPIO3)                               |
| SPI                   | SPI0: GPIO10/9/11/8/7; SPI1: GPIO20/19/21/18/17/16                            |
| UART                  | GPIO14 (TXD), GPIO15 (RXD)                                                    |
| Audio                 | PCM interface (GPIO18/19/20/21) used by HiFiBerry; 3.5 mm combo jack          |
| Video                 | Full-size HDMI, DSI display port, CSI camera port                             |
| Storage               | Micro SD card                                                                 |
| Power input           | 5 V / 2.5 A via micro USB, or 5 V via GPIO header pin 2/4                     |
| Power consumption     | Typically 1.1–1.5 A idle; up to 2.5 A under heavy load with USB peripherals   |
| Operating temperature | 0–50 °C                                                                       |
| Dimensions            | 85 mm × 56 mm                                                                 |
| GPIO logic level      | 3.3 V (NOT 5 V tolerant — do not apply 5 V to GPIO pins)                      |

> *The HiFiBerry Amp2 powers the Raspberry Pi from the 12–24 V supply via an onboard voltage converter. No separate 5 V micro USB supply is needed when the HiFiBerry is fitted.*

#### GPIO Header Pinout (BCM Numbering)

The 40-pin GPIO header uses BCM (Broadcom) pin numbering throughout the RPiOperant codebase. The physical pin layout is two columns of 20 pins; pin 1 (3.3 V) is at the end closest to the SD card slot.

|                  |              |                      |                                         |
| ---------------- | ------------ | -------------------- | --------------------------------------- |
| **Physical Pin** | **BCM GPIO** | **Default Function** | **RPiOperant Use**                      |
| 1                | —            | \+3.3 V              | Power                                   |
| 2                | —            | \+5 V                | Power                                   |
| 3                | GPIO2        | SDA1 (I2C)           | I2C data — both PCA9685 chips           |
| 5                | GPIO3        | SCL1 (I2C)           | I2C clock — both PCA9685 chips          |
| 7                | GPIO4        | GPCLK0               | HiFiBerry mute                          |
| 8                | GPIO14       | TXD (UART)           | Serial transmit / 50-pin IDC pin 29     |
| 10               | GPIO15       | RXD (UART)           | Serial receive / 50-pin IDC pin 31      |
| 11               | GPIO17       | GPIO                 | Load cell DAT (HX711)                   |
| 13               | GPIO27       | GPIO                 | Auxiliary GPIO / 50-pin IDC pin 28 area |
| 15               | GPIO22       | GPIO                 | Auxiliary GPIO                          |
| 16               | GPIO23       | GPIO                 | AUX IR 1                                |
| 18               | GPIO24       | GPIO                 | AUX IR 2                                |
| 19               | GPIO10       | SPI0 MOSI            | AUX IR 6                                |
| 21               | GPIO9        | SPI0 MISO            | AUX IR 4                                |
| 22               | GPIO25       | GPIO                 | AUX IR 3                                |
| 23               | GPIO11       | SPI0 SCLK            | AUX IR 5                                |
| 24               | GPIO8        | SPI0 CE0             | Load cell CLK (HX711)                   |
| 26               | GPIO7        | SPI0 CE1             | AUX IR 7                                |
| 29               | GPIO5        | GPIO                 | Hopper IR sense                         |
| 31               | GPIO6        | GPIO                 | Left IR sense                           |
| 32               | GPIO12       | PWM0                 | AUX IR 8                                |
| 33               | GPIO13       | PWM1                 | Center IR sense                         |
| 35               | GPIO19       | PCM FS               | HiFiBerry PCM frame sync                |
| 36               | GPIO16       | GPIO                 | 50-pin IDC pin 28 (GPIO\_16)            |
| 37               | GPIO26       | GPIO                 | Right IR sense                          |
| 38               | GPIO20       | PCM DIN              | HiFiBerry PCM data in                   |
| 40               | GPIO21       | PCM DOUT             | HiFiBerry PCM data out                  |

### B.2 HiFiBerry Amp2 (v1.0)

The HiFiBerry Amp2 is a DAC and Class-D stereo amplifier HAT designed for all Raspberry Pi models with a 40-pin GPIO header. It sits directly on top of the Raspberry Pi inside the MagPi client enclosure and provides amplified audio output to the speaker as well as powering the Raspberry Pi from the main 12–24 V supply.

Official datasheet: hifiberry.com/docs/data-sheets/datasheet-amp2/

|                                          |                                                                     |
| ---------------------------------------- | ------------------------------------------------------------------- |
| **Parameter**                            | **Value**                                                           |
| Interface to RPi                         | PCM I2S (GPIO18/19/20/21) for audio; I2C for control                |
| DAC resolution                           | 24-bit                                                              |
| Supported sample rates                   | 44.1, 48, 88.2, 96, 176.4, 192 kHz                                  |
| Amplifier topology                       | Class-D stereo                                                      |
| Speaker impedance                        | 4–8 Ω                                                               |
| Recommended supply voltage               | 12–20 V                                                             |
| Absolute maximum supply voltage          | 24 V                                                                |
| THD+N                                    | \<0.02% typical (output power 0.1–10 W)                             |
| SNR                                      | 104 dB typical                                                      |
| Frequency response                       | 20–20,000 Hz                                                        |
| Typical output power (4 Ω, THD+N \<0.1%) | 14 W @ 12 V; 18 W @ 18 V; 20 W @ 24 V per channel                   |
| Typical output power (8 Ω, THD+N \<0.1%) | 8 W @ 12 V; 17 W @ 18 V; 28 W @ 24 V per channel                    |
| Maximum output power (4 Ω, THD+N \<10%)  | 15 W @ 12 V; 30 W @ 18 V; 44 W @ 24 V per channel                   |
| Maximum output power (8 Ω, THD+N \<10%)  | 10 W @ 12 V; 20 W @ 18 V; 38 W @ 24 V per channel                   |
| Powers Raspberry Pi                      | Yes — onboard voltage converter; no separate USB supply needed      |
| Linux driver                             | hifiberry-dacplus (dtoverlay=hifiberry-dacplus in /boot/config.txt) |
| L/R channel bridging                     | Not supported                                                       |

> *The MagPi client uses a 12 V supply. With 4 Ω speakers at 12 V the typical output per channel is 14 W, which is more than sufficient for the small speakers used inside the sound isolation chambers.*
> *The speaker connector polarity on the Amp2 is reversed on one channel compared to the older Amp+. Always check the PCB silkscreen markings when connecting speakers.*

### B.3 NXP PCA9685 16-Channel PWM Controller

The PCA9685 is an I2C-controlled 16-channel, 12-bit PWM LED/servo controller made by NXP Semiconductors. Two instances are used on the RPiOperant Rev D board: one for LED and house light control (U1, address 0x55) and one for servo control (U7, address 0x45).

Official datasheet: nxp.com/docs/en/data-sheet/PCA9685.pdf

|                            |                                                                                              |
| -------------------------- | -------------------------------------------------------------------------------------------- |
| **Parameter**              | **Value**                                                                                    |
| Manufacturer               | NXP Semiconductors                                                                           |
| Part number (board)        | PCA9685PW (TSSOP-28 package)                                                                 |
| Number of PWM channels     | 16 (independent)                                                                             |
| PWM resolution             | 12-bit (4096 steps per channel)                                                              |
| PWM frequency range        | Typically 24–1526 Hz (programmable via prescaler)                                            |
| PWM frequency: U1 (lights) | 1000 Hz                                                                                      |
| PWM frequency: U7 (servo)  | 50 Hz                                                                                        |
| Supply voltage (VDD)       | 2.3–5.5 V                                                                                    |
| I/O voltage tolerance      | 5.5 V (5 V safe — compatible with 3.3 V RPi GPIO)                                            |
| Output current per channel | 25 mA sink (open-drain) or 25 mA sink / 10 mA source (totem-pole)                            |
| Total output current       | 400 mA maximum across all channels                                                           |
| I2C bus                    | Fast-mode Plus (Fm+) up to 1 MHz; also compatible with standard (100 kHz) and fast (400 kHz) |
| I2C address format         | 1 A5 A4 A3 A2 A1 A0 R/W (base 0x40; address pins set via A0–A5)                              |
| I2C address U1 (lights)    | 0x55 (A0, A2, A4 pulled high)                                                                |
| I2C address U7 (servo)     | 0x45 (A0, A2 pulled high)                                                                    |
| External clock input       | Up to 50 MHz (replaces internal 25 MHz oscillator when used)                                 |
| Power-on reset             | Yes — all outputs disabled at reset                                                          |
| Package                    | TSSOP-28 (body 4.4 mm wide)                                                                  |

#### PWM Frequency Calculation

The PWM output frequency is set by writing a prescale value to the PRE\_SCALE register. The formula is:

```
prescale = round(osc_clock / (4096 * update_rate)) - 1
```

where osc\_clock is 25 MHz and update\_rate is the desired frequency in Hz. Examples:

|                      |                    |                      |
| -------------------- | ------------------ | -------------------- |
| **Target frequency** | **Prescale value** | **Actual frequency** |
| 1000 Hz (lights)     | 5                  | 1049 Hz              |
| 50 Hz (servos)       | 121                | 51.6 Hz              |
| 200 Hz               | 30                 | 200.3 Hz             |

> *The prescale value can only be changed when the chip is in sleep mode (SLEEP bit = 1 in MODE1). The RPiOperant code handles this automatically in the PWM class set\_frequency() method in raspi\_gpio\_.py.*

#### Address Pin Reference

Each address pin (A0–A5) that is pulled high adds the corresponding value to the base address 0x40. Pins left floating must be tied to GND — do not leave them unconnected.

|         |                         |
| ------- | ----------------------- |
| **Pin** | **Value added to 0x40** |
| A0      | 0x01                    |
| A1      | 0x02                    |
| A2      | 0x04                    |
| A3      | 0x08                    |
| A4      | 0x10                    |
| A5      | 0x20                    |

### B.4 Texas Instruments SN74LVC14A Hex Schmitt-Trigger Inverter

The SN74LVC14A is a hex (6-channel) inverting Schmitt-trigger buffer. On the RPiOperant Rev D board it is used to interface the IR beam emitter/detector pairs: the IR detector output is an active-low open-collector signal, which the SN74LVC14A squares up and inverts to produce a clean active-high digital signal for the Raspberry Pi GPIO. Two devices are fitted (12 channels total), powered from the +3.3 V rail.

Official datasheet: ti.com/product/SN74LVC14A

|                                |                                                              |
| ------------------------------ | ------------------------------------------------------------ |
| **Parameter**                  | **Value**                                                    |
| Manufacturer                   | Texas Instruments                                            |
| Channels                       | 6 independent inverting Schmitt-trigger buffers              |
| Supply voltage (VCC)           | 1.65–3.6 V (SN74LVC14A); compatible with 3.3 V RPi GPIO rail |
| Input voltage tolerance        | 5.5 V (inputs 5 V tolerant at any valid VCC)                 |
| Output current (IOL / IOH)     | 24 mA sink / 24 mA source                                    |
| Propagation delay (tpd)        | 5–10 ns typical @ 3.3 V                                      |
| Schmitt threshold VT+ @ 3.3 V  | typ 1.5 V (min 0.9 V, max 2.5 V)                             |
| Schmitt threshold VT− @ 3.3 V  | typ 0.9 V (min 0.3 V, max 1.6 V)                             |
| Hysteresis (VT+ − VT−) @ 3.3 V | typ 0.5 V                                                    |
| Logic function                 | Y = ¬A (inverting)                                           |
| Package (board)                | 14-pin TSSOP (SN74LVC14AQDRQ1 automotive-grade)              |
| Operating temperature          | −40 to +125 °C                                               |
| Quiescent supply current       | 10 μA max                                                    |
| Partial power-down protection  | Yes (Ioff — outputs disabled when VCC = 0 V)                 |

> *The inverting output means IR beam ‘blocked’ (detector dark → open-collector high → SN74LVC14A input high) produces a LOW output to the RPi GPIO. PyOperant compensates with inverted=True in the panel configuration for all IR beam inputs.*

### B.5 Texas Instruments TPSM64404RCHR Dual-Output Power Module

The TPSM64404RCHR is a dual-output synchronous step-down DC/DC power module from Texas Instruments. It integrates the switching controller, power MOSFETs, inductor, and passives into a single package. On the RPiOperant Rev D board it converts the 12 V supply rail into two lower-voltage rails: +12 V (regulated, for house lights) and +6 V (for the servo).

Official datasheet: ti.com/product/TPSM64404

|                                     |                                                           |
| ----------------------------------- | --------------------------------------------------------- |
| **Parameter**                       | **Value**                                                 |
| Manufacturer                        | Texas Instruments                                         |
| Part number                         | TPSM64404RCHR                                             |
| Topology                            | Dual synchronous step-down (buck) power module            |
| Input voltage range                 | 4–14 V (board uses 12 V nominal input)                    |
| Output voltage range (each channel) | 0.8–16 V (set by external resistor)                       |
| Output current (each channel)       | 2 A continuous                                            |
| Total output current                | 4 A (2 A per channel, both channels independent)          |
| Switching frequency                 | 600 kHz typical                                           |
| Efficiency                          | Up to ≈95% typical (dependent on VIN/VOUT ratio and load) |
| Output 1 (board config)             | \+12 V (house lights via SQ2364EES MOSFET driver)         |
| Output 2 (board config)             | \+6 V (servo supply via 50-pin IDC pin 4)                 |
| Protections                         | Overcurrent, overtemperature, undervoltage lockout (UVLO) |
| Package                             | RCHR (3.5 mm × 5.5 mm QFN with exposed pad)               |
| Operating temperature               | −40 to +85 °C ambient                                     |

> *The board’s input supply is 12 V from an external DC adapter. The TPSM64404 minimum input voltage is 4 V, so any supply between 4 V and 14 V will work electrically, but the output voltages are set by fixed resistors and will only be correct at the design input voltage of 12 V. Do not exceed 14 V on the board input.*

### B.6 Vishay SQ2364EES N-Channel MOSFET (House Light Driver)

The SQ2364EES is a small N-channel enhancement-mode MOSFET in a SOT-363 (6-pin) package. On the RPiOperant Rev D board it is used as a low-side switch to drive the house light load from the +12 V rail, controlled by a PCA9685 PWM output via the gate pin.

Official datasheet: vishay.com (search SQ2364EES)

|                                  |                                   |
| -------------------------------- | --------------------------------- |
| **Parameter**                    | **Value**                         |
| Manufacturer                     | Vishay                            |
| Part number                      | SQ2364EES-T1\_GE3                 |
| Polarity                         | N-channel enhancement mode        |
| Drain-source voltage (VDS)       | 60 V                              |
| Continuous drain current (ID)    | 2 A                               |
| On-resistance (RDS(on))          | 0.19 Ω @ VGS = 4.5 V              |
| Gate threshold voltage (VGS(th)) | 600 mV typical (logic-level gate) |
| Gate drive voltage (VGS)         | Max ±12 V                         |
| Package                          | SOT-363 (6-pin SMD)               |
| AEC-Q100 qualified               | Yes (automotive grade)            |
| Max junction temperature         | 175 °C                            |

> *The gate is driven by a PCA9685 output (3.3 V logic). The SQ2364EES has a very low threshold voltage (600 mV typ) so it turns on fully at 3.3 V gate drive. RDS(on) of 0.19 Ω at 2 A gives a power dissipation of under 0.8 W in the SOT-363 package, which is within its rated capability.*

### B.7 AVIA Semiconductor HX711 24-Bit ADC (Load Cell Amplifier)

The HX711 is a precision 24-bit sigma-delta analog-to-digital converter designed for direct interface with strain gauge bridge sensors (load cells). On the RPiOperant Rev D board it reads the load cell fitted to the hopper to measure the weight of food in the hopper. It communicates with the Raspberry Pi via a simple two-wire serial interface: DAT on GPIO17 and CLK on GPIO8.

Official datasheet: cdn.sparkfun.com/datasheets/Sensors/ForceFlex/hx711\_english.pdf

|                                               |                                                                        |
| --------------------------------------------- | ---------------------------------------------------------------------- |
| **Parameter**                                 | **Value**                                                              |
| Manufacturer                                  | AVIA Semiconductor (Xiamen)                                            |
| Part number                                   | HX711                                                                  |
| ADC resolution                                | 24-bit                                                                 |
| ADC type                                      | Sigma-delta                                                            |
| Input channels                                | 2 differential (Channel A and Channel B)                               |
| Channel A gain                                | Selectable: 128 or 64                                                  |
| Channel B gain                                | Fixed: 32                                                              |
| Full-scale input (Ch A, gain 128, AVDD = 5 V) | ±20 mV differential                                                    |
| Full-scale input (Ch A, gain 64, AVDD = 5 V)  | ±40 mV differential                                                    |
| Supply voltage (VSUP / AVDD)                  | 2.6–5.5 V (board supplies 3.3 V)                                       |
| Output data rate                              | 10 Hz or 80 Hz (selected by RATE pin)                                  |
| 50/60 Hz supply noise rejection               | Yes (simultaneous)                                                     |
| Interface                                     | 2-wire serial: DAT (data out) and PD\_SCK (clock / power-down control) |
| RPi connections (BCM)                         | DAT → GPIO17; PD\_SCK → GPIO8                                          |
| Operating current (normal)                    | \<1.6 mA                                                               |
| Operating current (power down)                | \<1 μA                                                                 |
| On-chip oscillator                            | Yes — no external crystal required                                     |
| On-chip power supply regulator                | Yes — provides regulated AVDD for load cell excitation                 |
| Package                                       | SOP-16                                                                 |
| Operating temperature                         | −40 to +85 °C                                                          |

> *The gain and active channel are selected by the number of clock pulses sent per conversion cycle: 25 pulses = Channel A gain 128; 26 pulses = Channel B gain 32; 27 pulses = Channel A gain 64. The pyoperant codebase uses Channel A at gain 128 (the default 25-pulse mode).*
> *Power-down is triggered by holding PD\_SCK high for more than 60 μs. The chip resets and re-reads the RATE pin on wake-up, so power cycling the HX711 via GPIO8 is the cleanest way to reset it after a communication error.*

### B.8 GoBilda 2000-0025-0002 Dual Mode Servo (Hopper Actuator)

The GoBilda 2000-0025-0002 (25-2 Torque) is a standard-size brushed DC servo with a 300:1 steel gear train and 5 kΩ potentiometer feedback. It is the hopper actuator on the RPiOperant Rev D panel, driven by the servo PCA9685 (U7, address 0x45) at 50 Hz. The servo supports two operating modes; only position mode is used in the RPiOperant codebase.

Product page: gobilda.com/2000-series-dual-mode-servo-25-2-torque/

|                                  |                                                              |
| -------------------------------- | ------------------------------------------------------------ |
| **Parameter**                    | **Value**                                                    |
| Manufacturer                     | goBILDA                                                      |
| SKU                              | 2000-0025-0002                                               |
| Weight                           | 60 g                                                         |
| Gear ratio                       | 300:1                                                        |
| Gear material                    | Steel                                                        |
| Output shaft                     | 25-tooth spline                                              |
| Output shaft support             | Dual ball bearing                                            |
| Motor type                       | Brushed DC                                                   |
| Position feedback                | 5 kΩ potentiometer                                           |
| Operating voltage                | 4.8–7.4 V (board supplies +6 V ✔)                            |
| No-load speed @ 6 V              | 0.20 sec / 60° (50 RPM)                                      |
| Stall torque @ 6 V               | 300 oz·in (21.6 kg·cm)                                       |
| No-load current @ 6 V            | 160 mA                                                       |
| Stall current @ 6 V              | 2500 mA                                                      |
| PWM frame period                 | 20 ms (50 Hz)                                                |
| PWM range — position mode        | 500–2500 μs                                                  |
| PWM range — continuous mode      | 900–2100 μs                                                  |
| Angular travel per μs            | 0.150° / μs                                                  |
| Maximum rotation (position mode) | 300°                                                         |
| Deadband width                   | 4 μs                                                         |
| Direction with increasing PWM    | Clockwise                                                    |
| Signal amplitude                 | 3–5 V (3.3 V RPi GPIO compatible ✔)                          |
| Connector                        | 3-position TJC8 / MH-FC (standard servo color coding)        |
| Wire                             | 22 AWG, 300 mm, signal = orange, +V = red, GND = brown/black |
| Servo size class                 | Standard                                                     |

#### Position Mode Pulse Width Reference

In position mode the servo shaft angle is proportional to the PWM pulse width. The full 300° travel spans 500–2500 μs (a 2000 μs range), giving 0.150° per microsecond.

|                      |                                |                                                |
| -------------------- | ------------------------------ | ---------------------------------------------- |
| **Pulse width (μs)** | **PCA9685 duty cycle @ 50 Hz** | **Shaft position**                             |
| 500                  | 2.5%                           | Full anti-clockwise end (0° of 300° range)     |
| 900                  | 4.5%                           | Typical hopper DOWN position (start of travel) |
| 1500                 | 7.5%                           | Mechanical center (150°)                       |
| 2100                 | 10.5%                          | Typical hopper UP position (mid–upper travel)  |
| 2500                 | 12.5%                          | Full clockwise end (300° of 300° range)        |

The PCA9685 duty cycle value written to the register is calculated from the pulse width:

```
counts = round(pulse_us / 20000 * 4096) # at 50 Hz, period = 20000 us
```

Examples: 500 μs → counts = 102; 1500 μs → counts = 307; 2500 μs → counts = 512.

> *The actual hopper up\_angle and down\_angle values are calibrated per panel in local\_pi\_revd.py and will differ from the table above. The table gives the full range of safe travel. Never command a pulse width below 500 μs or above 2500 μs — these are the hardware limits of the potentiometer feedback and may damage the gear train if exceeded.*
> *The servo operates in position mode by default. Continuous rotation mode requires the goBILDA 3102-0001-0001 Dual Mode Servo Programr to toggle; do not use the continuous-mode PWM range (900–2100 μs) in position mode as the center point (1500 μs) will be interpreted as stop rather than center position.*

### B.9 Molex KK 254 (.100") Connector Part Numbers

The RPiOperant panel wiring uses Molex KK 254 series (.100" / 2.54 mm pitch) connectors throughout. These are single-row, wire-to-board connectors with a polarising key and friction latch. The female housing crimps onto the wire harness; the male pin header is soldered to the PCB. Crimp terminals accept 22–28 AWG wire.

|                            |              |                       |                                       |
| -------------------------- | ------------ | --------------------- | ------------------------------------- |
| **Item**                   | **Circuits** | **Molex part number** | **Use on panel**                      |
| Female housing             | 2            | 22-01-2021            | Power, single sensors                 |
| Female housing             | 3            | 22-01-2031            | IR beam (signal + power + GND), servo |
| Female housing             | 4            | 22-01-2041            | Load cell (4-wire bridge)             |
| Female housing             | 5            | 22-01-2051            | Speaker, RGB LED                      |
| Male PCB header (straight) | 2            | 22-23-2021            | Board-side 2-pin                      |
| Male PCB header (straight) | 3            | 22-23-2031            | Board-side 3-pin                      |
| Male PCB header (straight) | 4            | 22-23-2041            | Board-side 4-pin                      |
| Male PCB header (straight) | 5            | 22-23-2051            | Board-side 5-pin                      |
| Crimp terminal (tin)       | —            | 08-50-0114            | 22–28 AWG, all housings               |

> *All KK 254 female housings are polarised — the key prevents reverse insertion. When assembling harnesses, ensure pin 1 (the end nearest the polarising key) matches the PCB header pin 1 marking. The crimp terminal 08-50-0114 is the standard tin-plated version; gold-plated 08-50-0113 is also compatible and preferred for low-voltage signal lines where contact resistance matters.*

## Appendix C: Python 3 Migration Notes

All changes made to migrate pyoperant from Python 2 to Python 3. All 22 unit tests pass on Python 3.14 after applying these changes. The last Python 2.7-compatible release is tagged V2-final on GitHub (github.com/gentnerlab/pyoperant/releases/tag/V2-final).

### C.1 Phase 2 — Syntax (hard errors in Python 3)

#### print statements → print() calls

|                                           |          |                                                        |
| ----------------------------------------- | -------- | ------------------------------------------------------ |
| **File**                                  | **Line** | **Change**                                             |
| pyoperant/utils.py                        | 201      | print "box number..." → print("box number...")         |
| pyoperant/utils.py                        | 204      | print "subject number..." → print("subject number...") |
| pyoperant/behavior/three\_ac\_matching.py | 128      | print parameters → print(parameters)                   |
| pyoperant/behavior/three\_ac\_matching.py | 129      | print PANELS → print(PANELS)                           |
| pyoperant/behavior/TargObjObj.py          | 47       | print e → print(e)                                     |
| pyoperant/interfaces/console\_.py         | 18       | print value → print(value)                             |

Note: pyoperant/local\_vogel.py already uses print(...) with parentheses — no change needed.

#### except E, e: → except E as e:

|                                  |          |                                               |
| -------------------------------- | -------- | --------------------------------------------- |
| **File**                         | **Line** | **Change**                                    |
| pyoperant/utils.py               | 104      | except Exception, e: → except Exception as e: |
| pyoperant/behavior/TargObjObj.py | 46       | except Exception, e: → except Exception as e: |

#### Relative imports in pyoperant/behavior/\_\_init\_\_.py

```
# Before
from two_alt_choice import *
from lights import *
from place_pref import PlacePrefExp
from place_pref_24hr import PlacePrefExp24hr
# After
from .two_alt_choice import *
from .lights import *
from .place_pref import PlacePrefExp
from .place_pref_24hr import PlacePrefExp24hr
```

### C.2 Phase 3 — Built-ins and stdlib

#### xrange → range

|                                           |                        |
| ----------------------------------------- | ---------------------- |
| **File**                                  | **Lines**              |
| pyoperant/behavior/three\_ac\_matching.py | 26, 28                 |
| pyoperant/behavior/TargObjObj.py          | 55, 82, 86, 87, 90, 91 |

Simple global find-and-replace of xrange with range in both files.

#### raw\_input → input

|                                   |          |
| --------------------------------- | -------- |
| **File**                          | **Line** |
| pyoperant/panels.py               | 58       |
| pyoperant/interfaces/console\_.py | 13       |
| scripts/tune\_servo.py            | 92       |
| scripts/test\_panel.py            | 69       |

#### cPickle → pickle

pyoperant/queues.py line 3:

```
# Before
import cPickle as pickle
# After
import pickle
```

pyoperant/behavior/text\_markov.py line 17:

```
# Before
import cPickle
# After
import pickle as cPickle # preserves all downstream cPickle.load/dump calls
```

#### basestring → str

pyoperant/utils.py line 150:

```
# Before
if isinstance(command, basestring):
# After
if isinstance(command, str):
```

### C.3 Phase 4 — Behavior changes requiring care

#### string.maketrans / two-arg str.translate in pyoperant/utils.py

The check\_cmdline\_params function used the Python 2-only two-argument form of str.translate to strip non-digit characters. Replace the entire function and remove import string from the top of utils.py:

```
# Before
def check_cmdline_params(parameters, cmd_line):
allchars = string.maketrans('','')
nodigs = allchars.translate(allchars, string.digits)
if not ('box' not in cmd_line or cmd_line['box'] == int(
parameters['panel_name'].encode('ascii','ignore').translate(allchars, nodigs))):
print "box number doesn't match config and command line"
return False
if not ('subj' not in cmd_line or int(
cmd_line['subj'].encode('ascii','ignore').translate(allchars, nodigs)) ==
int(parameters['subject'].encode('ascii','ignore').translate(allchars, nodigs))):
print "subject number doesn't match config and command line"
return False
return True
# After
def check_cmdline_params(parameters, cmd_line):
def digits_only(s):
return ''.join(c for c in s if c.isdigit())
if not ('box' not in cmd_line or cmd_line['box'] == int(digits_only(parameters['panel_name']))):
print("box number doesn't match config and command line")
return False
if not ('subj' not in cmd_line or
int(digits_only(cmd_line['subj'])) == int(digits_only(parameters['subject']))):
print("subject number doesn't match config and command line")
return False
return True
```

#### dict.items() indexing in pyoperant/behavior/three\_ac\_matching.py

In Python 3, dict.items() returns a view, not a list, so it cannot be indexed directly.

```
# Before (line 35)
motif_names, motif_files = zip(*[self.parameters['stims'].items()[mid] for mid in mids])
# After
motif_names, motif_files = zip(*[list(self.parameters['stims'].items())[mid] for mid in mids])
```

#### unicode() calls in pyoperant/behavior/text\_markov.py

All strings are unicode by default in Python 3. Replace all unicode("...", "utf-8") calls with plain string literals (lines 103–124):

```
# Before
stim_dict[unicode("class", "utf-8")] = ...
stim_dict[unicode("stim_name", "utf-8")] = ...
stim_dict[unicode("seq", "utf-8")] = ...
stim_dict[unicode("order", "utf-8")] = ...
stim_dict[unicode("syll_time_lens", "utf-8")] = ...
# After
stim_dict["class"] = ...
stim_dict["stim_name"] = ...
stim_dict["seq"] = ...
stim_dict["order"] = ...
stim_dict["syll_time_lens"] = ...
```

## Appendix D: Index

Section numbers are given. Where a topic spans multiple sections the primary reference is listed first.

**A**

ABCategory / ABCategory2 (protocol) — 8

address pins, PCA9685 — 3.6, B.3

audio output — see HiFiBerry, PyAudio — 3.2, 4.5, B.2

AUX\_LED channels (U1) — 3.2

AUX\_SERVO channels (U7) — 3.2

auxiliary servo outputs (local\_pi\_revd.py) — 6.3

**B**

BaseExp (class) — 2.2, 10.1, 10.5

behave (command-line script) — 9.1, 10.4

block\_design (config parameter) — 10.5

BooleanInput (hwio class) — 2.5, 6.3

BooleanOutput (hwio class) — 2.5, 6.3

breakout board — 4.1

board revision detection — see /etc/magpi\_revision — 6.2

**C**

cPickle — Python 3 migration — C.1, C.2

classes (config parameter) — 10.5

components.py — 2.4, 12.1

config.json — 10.5

correction\_trials (config parameter) — 10.5

cue light — see RGBLight — 2.4, 6.3

cue\_probability (protocol) — 8

CueSwitchExperiment (protocol) — 8

**D**

data files (CSV, log, summaryDAT) — 11.1

DATAPATH (config variable) — 6.2

debug (config parameter) — 10.5

DelayedMatch2 (protocol) — 8

down\_angle — see servo angle tuning — 6.4

**E**

ephem (dependency) — 6.1, C.1

EvidenceAccumExperiment (protocol) — 8

experiment\_path (config parameter) — 10.5

experimenter (config parameter) — 10.5

**F**

feed() method (Hopper) — 2.4

FirstOrder (protocol) — 8

food hopper — see Hopper — 4.2

free\_food\_schedule (config parameter) — 10.5

**G**

glab\_behaviors — see py-behaviors — 8

GPIO pin assignments (Rev C) — 6.3

GPIO pin assignments (Rev D) — 3.3, 6.3

**H**

HiFiBerry Amp2 (audio board) — 3.2, B.2

HOPPER\_SERVO\_CHANNEL constant — 6.3

HopperAlreadyUpError — 2.4, 9.3

HopperWontComeUpError — 2.4, 9.3

HopperWontDropError — 2.4, 9.3

Hopper (component class) — 2.4, 6.3

house light — see LEDStripHouseLight — 2.4, 4.4, 6.3

hwio.py — 2.5, 12.1

**I**

I2C bus — 3.3

i2cdetect — 9.3, 12.2

idle\_poll\_interval (config parameter) — 10.5

intertrial\_min (config parameter) — 10.5

inverted (parameter) — 3.2, 6.3

IR beam sensor — 3.2, 4.3, B.4

**L**

LEDStripHouseLight (component class) — 2.4, 4.4, 6.3

light\_schedule (config parameter) — 10.5

local.py (router) — 2.3, 6.2, 12.1

local\_pi\_revc.py — 6.2, 6.3, 12.1

local\_pi\_revd.py — 6.2, 6.3, 12.1

log file — 9.2, 11.1

log\_handlers (config parameter) — 10.5

**M**

MagPi client (hardware) — 3.1, 3.2

MagPi server — 5.2

/etc/magpi\_revision (revision file) — 6.2

Molex KK 254 connectors — B.9

**N**

network configuration — 5.1

no\_response\_correction\_trials (config parameter) — 10.5

**O**

operant conditioning (concept) — 1.1

open() mode — Python 3 migration — C.1, C.2

**P**

panel\_name (config parameter) — 10.5

panels.py / BasePanel — 2.3, 12.1

PCA9685 (U1, lights chip) — 3.2, 3.6, B.3

PCA9685 (U7, servo chip) — 3.2, 3.6, B.3

peck port — see PeckPort — 4.3

PeckPort (component class) — 2.4, 6.3

pigpio / pigpiod — 6.1, 9.1, 12.2

print statements — Python 3 migration — C.1, C.2

PWMOutput (hwio class) — 2.5, 6.3

py-behaviors repository — 8

Python 3 migration — Appendix C

**Q**

queues.py (trial queue classes) — 11.1, 12.1

**R**

raspi\_gpio\_.py (interface) — 2.5, 12.1

RaspberryPiInterface (class) — 2.5, 6.2

reinforcement (config parameter) — 10.5

reinforcement schedules — 10.5

reset() method — 2.3, 6.3

response\_win (config parameter) — 10.5

Rev C board — 6.2, 6.3

Rev D board — 3.1, 6.2, 6.3

RGBLight (component class) — 2.4, 6.3

rsync (data backup) — 5.2

**S**

SameDifProbs (protocol) — 8

scripts/behave — 10.4, 12.1

SecondOrder (protocol) — 8

self.cue — see RGBLight — 6.3

servo angle tuning — 6.4

session\_post() method — 2.2, 10.2

session\_pre() method — 2.2, 10.2

session\_schedule (config parameter) — 10.5

shape (config parameter) — 10.5

shaping protocols — see shape.py — 2.2, 12.1

solenoid hopper (Rev C) — 6.2, 6.3

song\_recognition (protocol) — 8

SSH access — 5.1, 5.2

stim\_path (config parameter) — 10.5

stims (config parameter) — 10.5

subject (config parameter) — 10.5

summaryDAT file — 11.1

**T**

test() method — 2.3, 6.5

50-pin IDC connector — 3.4

TwoAltChoiceExp (class) — 2.2, 8, 10.5

two\_alt\_choice.py — 12.1

**U**

U1 (lights PCA9685) — 3.2

U7 (servo PCA9685) — 3.2

unicode() — Python 3 migration — C.1, C.2

up\_angle — see servo angle tuning — 6.4

**W**

write\_summary() method — 11.1

**X**

xrange — Python 3 migration — C.1, C.2

XY\_context (protocol) — 8
