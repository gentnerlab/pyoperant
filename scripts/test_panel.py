#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_panel.py -- Run the full panel component test for a Magpi panel.

Detects the board revision from /etc/magpi_revision and loads the correct
panel configuration. Runs an autonomous pass followed by interactive user
confirmation for each component.

Usage:
    python test_panel.py [panel_id]

    panel_id defaults to 1 if not specified.

Requirements:
    - pigpiod must be running (sudo pigpiod)
    - /etc/magpi_revision must contain 'revc' or 'revd'
    - Run from the pyoperant repo root, or ensure pyoperant is on PYTHONPATH
"""

import sys

REVISION_FILE = '/etc/magpi_revision'

def load_panels():
    try:
        with open(REVISION_FILE, 'r') as f:
            revision = f.read().strip().lower()
    except IOError:
        print("ERROR: Cannot read %s." % REVISION_FILE)
        print("Set it with: echo 'revd' | sudo tee %s" % REVISION_FILE)
        sys.exit(1)

    if revision == 'revd':
        from pyoperant.local_pi_revd import PANELS
    elif revision == 'revc':
        from pyoperant.local_pi_revc import PANELS
    else:
        print("ERROR: Unknown board revision '%s' in %s. Expected 'revc' or 'revd'." % (revision, REVISION_FILE))
        sys.exit(1)

    print("Board revision: %s" % revision)
    return PANELS

def main():
    panel_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    try:
        PANELS = load_panels()
    except ImportError:
        print("ERROR: pyoperant not found. Run from the repo root or install with: pip install -e .")
        sys.exit(1)

    if str(panel_id) not in PANELS:
        print("ERROR: panel %d not found. Available panels: %s" % (panel_id, ', '.join(PANELS.keys())))
        sys.exit(1)

    print("Initialising panel %d..." % panel_id)
    try:
        panel = PANELS[str(panel_id)]()
    except Exception as e:
        print("ERROR initialising panel: %s" % e)
        print("Is pigpiod running? Try: sudo pigpiod")
        sys.exit(1)

    print("Panel %d initialised.\n" % panel_id)

    # --- Hopper servo note ---
    # The hopper up_angle and down_angle must be tuned for each physical panel.
    # Current values are set in PiPanel.__init__() in local_pi_revd.py.
    #
    # To find correct values for a new panel:
    #   python scripts/tune_servo.py
    #   (interactive: moves servo, reads IR beam, prints final values to copy
    #    into local_pi_revd.py)
    #
    # To check the current values:
    #   grep -A4 "components.Hopper" pyoperant/local_pi_revd.py
    #
    # To update after tuning, edit local_pi_revd.py:
    #   self.hopper = components.Hopper(IR=..., servo=...,
    #                                   up_angle=<tuned>,
    #                                   down_angle=<tuned>,
    #                                   inverted=False)
    #
    # Defaults (up_angle=45, down_angle=10) are starting points only.
    # A wrong up_angle means the hopper won't trip the IR beam → reward fails.
    # A wrong down_angle means the hopper won't park flush → IR false-positives.
    print("NOTE: Hopper servo angles must be tuned per panel.")
    print("      Current values are in local_pi_revd.py (PiPanel.__init__).")
    print("      To tune interactively: python scripts/tune_servo.py")
    print("")

    print("Inspect the board before proceeding.")
    try:
        resp = input("Press Enter to begin the test, or Ctrl+C to abort: ")
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)

    passed = panel.test()
    sys.exit(0 if passed else 1)

if __name__ == '__main__':
    main()
