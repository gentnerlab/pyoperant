#!/usr/bin/env python
"""
sync_mic_cal.py -- Pull this box's UMIK-1 calibration file from the
fleet's calibration-file registry on magpi.ucsd.edu, and record which
physical mic is installed here in this box's own panel_config.json.

Which UMIK-1 serial is installed in which box cannot be auto-detected --
the UMIK-1's USB descriptor reports a static serial string ("1") on every
unit, not its real calibration serial number (confirmed live, 2026-09-21).
So this is a manual, one-off-per-install step, run on the box itself, the
same way scripts/tune_servo.py's hopper calibration is -- not something
pyoperant discovers on its own at every session start.

Mic identity is a property of this physical box's hardware (whichever
UMIK-1 happens to be plugged in right now), not of whichever bird is
currently assigned to it -- same reasoning as hopper_up_angle/
hopper_down_angle, so it lives in panel_config.json too, not a subject's
config.json and not local_pi_revd.py. See pyoperant.utils.load_panel_config()
/ PiPanel.__init__ in local_pi_revd.py for how mic_serial is read back, and
pyoperant.song_recording.calibration for what the synced file is used for.

Usage:
    python3 sync_mic_cal.py <serial>
        Record <serial> as this box's mic_serial in panel_config.json,
        then fetch <serial>_90deg.txt from the server and save it locally
        (off-axis/diffuse-field calibration -- see calibration.py's module
        docstring for why, not the on-axis variant miniDSP also ships).
    python3 sync_mic_cal.py
        Re-sync using whatever mic_serial is already in panel_config.json
        (e.g. after the calibration file was corrected on the server, or
        after re-flashing this box without losing panel_config.json).

Requires this box's existing id_client_fleet SSH key/~/.ssh/config wiring
to the server (same mechanism update_fleet_code.py's git pulls already
rely on -- see project_data_pipeline_website memory) -- no new
credentials needed.
"""

import argparse
import json
import os
import subprocess
import sys

try:
    from pyoperant.utils import PANEL_CONFIG_PATH
except ImportError:
    PANEL_CONFIG_PATH = '/home/bird/panel_config.json'

try:
    from pyoperant.song_recording.calibration import DEFAULT_PATH as CAL_PATH
except ImportError:
    CAL_PATH = '/home/bird/mic_cal.txt'

SERVER_HOST = 'bird@192.168.1.100'
SERVER_CAL_DIR = '~/minidsp_mic_cal'


def _read_panel_config():
    if not os.path.isfile(PANEL_CONFIG_PATH):
        return {}
    with open(PANEL_CONFIG_PATH, 'r') as f:
        return json.load(f)


def _write_mic_serial(serial):
    """Merge mic_serial into panel_config.json, backing up any existing
    file first -- same pattern as tune_servo.py's own config write, minus
    the interactive confirmation prompt (this script is meant to be run
    non-interactively, e.g. orchestrated across the fleet from the
    server, not just typed at a local terminal one box at a time)."""
    panel_config = _read_panel_config()
    if panel_config.get('mic_serial') == serial:
        print("%s already has mic_serial=%s -- nothing to change."
              % (PANEL_CONFIG_PATH, serial))
        return

    if os.path.isfile(PANEL_CONFIG_PATH):
        backup_path = PANEL_CONFIG_PATH + '.bak_before_mic_serial_sync'
        with open(PANEL_CONFIG_PATH, 'r') as f:
            raw = f.read()
        with open(backup_path, 'w') as f:
            f.write(raw)
        print("Backed up existing %s -> %s" % (PANEL_CONFIG_PATH, backup_path))

    old_serial = panel_config.get('mic_serial')
    panel_config['mic_serial'] = serial
    with open(PANEL_CONFIG_PATH, 'w') as f:
        json.dump(panel_config, f, indent=2)
        f.write('\n')
    print("Wrote mic_serial: %r -> %r in %s" % (old_serial, serial, PANEL_CONFIG_PATH))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        'serial', nargs='?', default=None,
        help='UMIK-1 serial number to record and sync. Omit to re-sync '
             'using the serial already in panel_config.json.')
    args = parser.parse_args()

    serial = args.serial
    if serial is None:
        serial = _read_panel_config().get('mic_serial')
        if serial is None:
            print("No mic_serial in %s and none given on the command line -- "
                  "nothing to sync.\nUsage: python3 sync_mic_cal.py <serial>"
                  % PANEL_CONFIG_PATH)
            sys.exit(1)
    else:
        _write_mic_serial(serial)

    remote_path = '%s:%s/%s_90deg.txt' % (SERVER_HOST, SERVER_CAL_DIR, serial)
    print("Fetching %s -> %s ..." % (remote_path, CAL_PATH))
    result = subprocess.run(['scp', remote_path, CAL_PATH],
                             capture_output=True, text=True)
    if result.returncode != 0:
        print("scp failed:\n%s" % result.stderr)
        sys.exit(1)

    # Validate before declaring success -- a corrupt/wrong download should
    # be caught here, not silently left in place for a real recording
    # session to discover later.
    try:
        from pyoperant.song_recording.calibration import MicCalibration
    except ImportError as exc:
        print("Fetched the file but could not import pyoperant.song_recording "
              "to validate it (%s) -- check manually." % exc)
        return

    cal = MicCalibration.load(CAL_PATH)
    if cal is None:
        print("Fetched file did not parse as a valid calibration file -- "
              "check %s manually." % CAL_PATH)
        sys.exit(1)
    if cal.serial != serial:
        print("WARNING: fetched file's own header says serial=%s, but "
              "expected %s -- mismatch in the server's registry itself, "
              "not just this sync. Check ~/minidsp_mic_cal/ on the server."
              % (cal.serial, serial))
        sys.exit(1)

    print("OK: serial=%s sens_factor=%.2fdB saved to %s"
          % (cal.serial, cal.sens_factor_db, CAL_PATH))


if __name__ == '__main__':
    main()
