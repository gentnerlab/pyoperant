#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_ir.py -- Live IR beam status display for Rev D Magpi panels.

Shows the current state of all IR sensors, updating continuously.
Press Ctrl+C to exit.

Usage:
    python test_ir.py
"""

import sys
import time

def main():
    try:
        from pyoperant.interfaces.raspi_gpio_ import RaspberryPiInterface
        from pyoperant import hwio
    except ImportError:
        print("ERROR: pyoperant not found. Run from the repo root or install with: pip install -e .")
        sys.exit(1)

    from pyoperant.local_pi_revd import LIGHTS_PCA9685_ADDRESS, SERVO_PCA9685_ADDRESS, INPUTS

    print("Connecting to hardware...")
    try:
        raspi = RaspberryPiInterface(
            device_name='ir_test',
            lights_address=LIGHTS_PCA9685_ADDRESS,
            servo_address=SERVO_PCA9685_ADDRESS)
    except Exception as e:
        print("ERROR connecting to hardware: %s" % e)
        print("Is pigpiod running? Try: sudo pigpiod")
        sys.exit(1)

    sensor_names = [
        'Hopper',
        'Left',
        'Center',
        'Right',
        'IR-1',
        'IR-2',
        'IR-3',
        'IR-4',
        'IR-5',
        'IR-6',
    ]

    sensors = []
    for channel in INPUTS:
        sensors.append(hwio.BooleanInput(interface=raspi, params={'channel': channel}))

    print("Connected. Monitoring IR beams -- press Ctrl+C to exit.\n")

    # column widths for alignment
    col = 10

    # header
    header = ''.join(name.ljust(col) for name in sensor_names)
    print(header)
    print('-' * len(header))

    try:
        while True:
            states = []
            for sensor in sensors:
                raw = sensor.read()
                states.append('BLOCKED' if raw else 'clear  ')
            line = ''.join(s.ljust(col) for s in states)
            sys.stdout.write('\r' + line)
            sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        raspi.close()

if __name__ == '__main__':
    main()
