#!/usr/bin/env python
"""
tune_servo.py -- Interactive servo angle tuning for Rev D Magpi hopper.

Run this script directly on the Raspberry Pi to find the correct up_angle
and down_angle values for a panel's hopper servo. Once you have good values
the script can write them directly back to local_pi_revd.py.

Usage:
    python tune_servo.py

Requirements:
    - pigpiod must be running (sudo pigpiod)
    - /etc/magpi_revision must contain 'revd'
    - Run from the pyoperant repo root, or ensure pyoperant is on PYTHONPATH
"""

import os
import re
import sys
import time

def _write_angles_to_config(up_angle, down_angle):
    """Offer to write tuned angles back to local_pi_revd.py."""
    # Locate local_pi_revd.py relative to this script
    # scripts/tune_servo.py -> pyoperant/local_pi_revd.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'pyoperant', 'local_pi_revd.py')
    config_path = os.path.normpath(config_path)

    if not os.path.isfile(config_path):
        print("\nCould not find local_pi_revd.py at %s" % config_path)
        print("Update manually:")
        print("  up_angle=%.1f, down_angle=%.1f" % (up_angle, down_angle))
        return

    with open(config_path, 'r') as f:
        original = f.read()

    # Replace up_angle=<number> and down_angle=<number> inside the Hopper() call.
    # Using a targeted pattern so we only touch the Hopper constructor, not any
    # other hypothetical uses of those keyword names elsewhere in the file.
    updated = re.sub(r'(components\.Hopper\(.*?)\bup_angle\s*=\s*[\d.]+',
                     lambda m: m.group(1) + ('up_angle=%.1f' % up_angle),
                     original, flags=re.DOTALL)
    updated = re.sub(r'(components\.Hopper\(.*?)\bdown_angle\s*=\s*[\d.]+',
                     lambda m: m.group(1) + ('down_angle=%.1f' % down_angle),
                     updated, flags=re.DOTALL)

    if updated == original:
        print("\nCould not locate up_angle/down_angle in %s" % config_path)
        print("Check that components.Hopper() is present and update manually.")
        return

    # Show what will change
    print("\nProposed changes to %s:" % os.path.relpath(config_path))
    old_lines = original.splitlines()
    new_lines = updated.splitlines()
    diff_shown = False
    for i, (old, new) in enumerate(zip(old_lines, new_lines)):
        if old != new:
            print("  line %d:  %s" % (i + 1, old.strip()))
            print("         -> %s" % new.strip())
            diff_shown = True
    if not diff_shown:
        print("  (no textual difference detected)")
        return

    try:
        resp = input("\nWrite these values to local_pi_revd.py? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        resp = 'n'

    if resp == 'y':
        with open(config_path, 'w') as f:
            f.write(updated)
        print("  -> %s updated." % os.path.relpath(config_path))
    else:
        print("  -> Not written. Update manually if needed.")


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
