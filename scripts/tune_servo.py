#!/usr/bin/env python
"""
tune_servo.py -- Interactive servo angle tuning for Rev D Magpi hopper.

Run this script directly on the Raspberry Pi to find the correct up_angle
and down_angle values for a panel's hopper servo. Once you have good values
the script can write them into this box's own panel_config.json as
hopper_up_angle/hopper_down_angle.

Hopper calibration is a property of this physical box's hardware (servo
mounting/mechanical tolerances), not of whichever bird happens to be
assigned to it right now -- it does NOT go in a subject's config.json
(that would get lost the next time a different bird is assigned here, and
there'd be no single place to find a box's last-known-good calibration),
and it does NOT go in local_pi_revd.py either (shared across the whole
fleet, must stay identical on every board so it can always be git-pulled
cleanly). See pyoperant.utils.load_panel_config() / PiPanel.__init__ in
local_pi_revd.py for how it's read back.

Usage:
    python tune_servo.py

Requirements:
    - pigpiod must be running (sudo pigpiod)
    - /etc/magpi_revision must contain 'revd'
    - Run from the pyoperant repo root, or ensure pyoperant is on PYTHONPATH
"""

import json
import os
import sys
import time

try:
    from pyoperant.utils import PANEL_CONFIG_PATH
except ImportError:
    PANEL_CONFIG_PATH = '/home/bird/panel_config.json'


def _write_angles_to_config(up_angle, down_angle):
    """Offer to write tuned angles into this box's panel_config.json as
    hopper_up_angle/hopper_down_angle."""
    if os.path.isfile(PANEL_CONFIG_PATH):
        with open(PANEL_CONFIG_PATH, 'r') as f:
            raw = f.read()
        try:
            panel_config = json.loads(raw)
        except ValueError as e:
            print("\nCould not parse %s as JSON: %s" % (PANEL_CONFIG_PATH, e))
            print("Add these manually:")
            print('  "hopper_up_angle": %.1f,' % up_angle)
            print('  "hopper_down_angle": %.1f,' % down_angle)
            return
    else:
        raw = None
        panel_config = {}

    old_up = panel_config.get('hopper_up_angle')
    old_down = panel_config.get('hopper_down_angle')
    if old_up == up_angle and old_down == down_angle:
        print("\n%s already has these exact values -- nothing to change." % PANEL_CONFIG_PATH)
        return

    print("\nProposed change to %s:" % PANEL_CONFIG_PATH)
    if raw is None:
        print("  (file does not exist yet -- will be created)")
    print("  hopper_up_angle:   %r -> %.1f" % (old_up, up_angle))
    print("  hopper_down_angle: %r -> %.1f" % (old_down, down_angle))

    try:
        resp = input("\nWrite these values to %s? [y/N]: " % PANEL_CONFIG_PATH).strip().lower()
    except (KeyboardInterrupt, EOFError):
        resp = 'n'

    if resp != 'y':
        print("  -> Not written. Update manually if needed.")
        return

    panel_config['hopper_up_angle'] = up_angle
    panel_config['hopper_down_angle'] = down_angle

    backup_msg = ""
    if raw is not None:
        backup_path = PANEL_CONFIG_PATH + '.bak_before_hopper_tuning'
        with open(backup_path, 'w') as f:
            f.write(raw)
        backup_msg = " (backup at %s)" % backup_path

    with open(PANEL_CONFIG_PATH, 'w') as f:
        json.dump(panel_config, f, indent=2)
        f.write('\n')
    print("  -> %s updated%s." % (PANEL_CONFIG_PATH, backup_msg))


def main():
    # --- connect to hardware ---
    try:
        import pigpio
    except ImportError:
        print("ERROR: pigpio not installed. Run: sudo apt install pigpio python-pigpio")
        sys.exit(1)

    try:
        from pyoperant.interfaces.raspi_gpio_ import RaspberryPiInterface
        from pyoperant import hwio
    except ImportError:
        print("ERROR: pyoperant not found. Run from the repo root or install with: pip install -e .")
        sys.exit(1)

    from pyoperant.local_pi_revd import LIGHTS_PCA9685_ADDRESS, SERVO_PCA9685_ADDRESS, INPUTS

    print("\n=== Rev D Hopper Servo Tuning ===\n")
    print("Connecting to pigpio...")

    try:
        raspi = RaspberryPiInterface(
            device_name='tune',
            lights_address=LIGHTS_PCA9685_ADDRESS,
            servo_address=SERVO_PCA9685_ADDRESS)
    except Exception as e:
        print("ERROR connecting to hardware: %s" % e)
        print("Is pigpiod running? Try: sudo pigpiod")
        sys.exit(1)

    print("Connected.\n")

    # hopper servo is channel 0 on the servo chip (HOPPER_SERVO_CHANNEL)
    servo = hwio.PWMOutput(interface=raspi, params={'channel': 0, 'servo': True})

    # hopper IR beam is INPUTS[0] = GPIO 5
    ir = hwio.BooleanInput(interface=raspi, params={'channel': INPUTS[0]})

    print("Controls:")
    print("  Enter a number (0.0 - 300.0) to move the servo to that angle in degrees")
    print("  'u'  = move to current up_angle")
    print("  'd'  = move to current down_angle")
    print("  'su' = set current angle as up_angle")
    print("  'sd' = set current angle as down_angle")
    print("  'i'  = read IR beam status")
    print("  'f'  = run a full feed cycle with current angles")
    print("  'q'  = quit and print final values\n")

    up_angle = None
    down_angle = None
    current_angle = None

    def read_ir():
        """Read IR beam. Returns True if beam is broken (hopper up). High = broken on Rev D."""
        raw = ir.read()
        broken = raw  # high = beam broken (hopper up)
        print("  IR beam: %s (raw=%s)" % ("BROKEN (hopper up)" if broken else "CLEAR (hopper down)", raw))
        return broken

    def move(angle):
        servo.write(angle)
        time.sleep(0.3)  # give servo time to move

    while True:
        try:
            prompt = "angle"
            if up_angle is not None:
                prompt += " [up=%.1f" % up_angle
                if down_angle is not None:
                    prompt += " down=%.1f" % down_angle
                prompt += "]"
            cmd = input("\n%s > " % prompt).strip().lower()
        except (KeyboardInterrupt, EOFError):
            cmd = 'q'

        if cmd == 'q':
            break

        elif cmd == 'i':
            read_ir()

        elif cmd == 'u':
            if up_angle is None:
                print("  up_angle not set yet. Enter a number first, then 'su' to set it.")
            else:
                print("  Moving to up_angle=%.1f" % up_angle)
                move(up_angle)
                current_angle = up_angle
                read_ir()

        elif cmd == 'd':
            if down_angle is None:
                print("  down_angle not set yet. Enter a number first, then 'sd' to set it.")
            else:
                print("  Moving to down_angle=%.1f" % down_angle)
                move(down_angle)
                current_angle = down_angle
                read_ir()

        elif cmd == 'su':
            if current_angle is None:
                print("  Move the servo to a position first.")
            else:
                up_angle = current_angle
                print("  up_angle set to %.1f" % up_angle)
                read_ir()

        elif cmd == 'sd':
            if current_angle is None:
                print("  Move the servo to a position first.")
            else:
                down_angle = current_angle
                print("  down_angle set to %.1f" % down_angle)
                read_ir()

        elif cmd == 'f':
            if up_angle is None or down_angle is None:
                print("  Set both up_angle and down_angle before running a feed cycle.")
            else:
                print("  Running feed cycle: up_angle=%.1f, down_angle=%.1f" % (up_angle, down_angle))
                print("  Moving UP...")
                move(up_angle)
                beam = read_ir()
                if not beam:
                    print("  WARNING: IR beam not tripped after moving up. up_angle may need adjustment.")
                else:
                    print("  Hopper confirmed UP. Waiting 2 seconds...")
                    time.sleep(2.0)
                print("  Moving DOWN...")
                move(down_angle)
                beam = read_ir()
                if beam:
                    print("  WARNING: IR beam still tripped after moving down. down_angle may need adjustment.")
                else:
                    print("  Hopper confirmed DOWN. Feed cycle complete.")

        else:
            try:
                angle = float(cmd)
                if not 0.0 <= angle <= 300.0:
                    print("  Value must be between 0.0 and 300.0 degrees")
                    continue
                print("  Moving to %.1f..." % angle)
                move(angle)
                current_angle = angle
                read_ir()
            except ValueError:
                print("  Unknown command. Enter a number, or: u/d/su/sd/i/f/q")

    # --- summary ---
    print("\n=== Tuning Complete ===\n")
    if up_angle is not None and down_angle is not None:
        print("Final values:")
        print("  up_angle   = %.1f" % up_angle)
        print("  down_angle = %.1f" % down_angle)
        _write_angles_to_config(up_angle, down_angle)
    else:
        print("No final angles recorded.")

    # park servo at down position if we have one
    if down_angle is not None:
        print("\nParking servo at down_angle=%.1f..." % down_angle)
        move(down_angle)

    raspi.close()
    print("Done.\n")

if __name__ == '__main__':
    main()
