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
    print("Inspect the board before proceeding.")
    try:
        resp = raw_input("Press Enter to begin the test, or Ctrl+C to abort: ")
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)

    passed = panel.test()
    sys.exit(0 if passed else 1)

if __name__ == '__main__':
    main()
