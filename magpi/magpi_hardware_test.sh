#!/bin/bash
# =============================================================================
# magpi_hardware_test.sh
# Post-reboot hardware verification for MagPi Rev D
# Run as bird after first boot and setup: bash ~/magpi_hardware_test.sh
# =============================================================================

LOG=$(mktemp)
trap "rm -f $LOG" EXIT

pass() { echo "  [PASS] $1"; echo "PASS" >> "$LOG"; }
fail() { echo "  [FAIL] $1"; echo "FAIL" >> "$LOG"; }

echo ""
echo "=== MagPi Rev D Hardware Test: $(date) ==="
echo ""

# -----------------------------------------------------------------------------
# 1. System
# -----------------------------------------------------------------------------
echo "[1/6] System"

REVISION=$(cat /etc/magpi_revision 2>/dev/null)
if [ "$REVISION" = "revd" ]; then
  pass "Board revision: revd"
else
  fail "Board revision: expected 'revd', got '${REVISION:-not set}'"
fi

HOSTNAME=$(hostname)
if [ -n "$HOSTNAME" ]; then
  pass "Hostname: $HOSTNAME"
else
  fail "Hostname not set"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -n "$IP" ]; then
  pass "IP address: $IP"
else
  fail "No IP address assigned"
fi

echo ""

# -----------------------------------------------------------------------------
# 2. I2C
# -----------------------------------------------------------------------------
echo "[2/6] I2C"

if ! command -v i2cdetect &>/dev/null; then
  fail "i2cdetect not found (i2c-tools not installed)"
else
  I2C_OUT=$(i2cdetect -y 1 2>/dev/null)
  if echo "$I2C_OUT" | grep -qw "45"; then
    pass "0x45 detected (servo/hopper PCA9685)"
  else
    fail "0x45 not found — servo/hopper PCA9685 not responding"
  fi
  if echo "$I2C_OUT" | grep -qw "55"; then
    pass "0x55 detected (lights PCA9685)"
  else
    fail "0x55 not found — lights PCA9685 not responding"
  fi
fi

echo ""

# -----------------------------------------------------------------------------
# 3. Audio
# -----------------------------------------------------------------------------
echo "[3/6] Audio"

APLAY_OUT=$(aplay -l 2>/dev/null)
if echo "$APLAY_OUT" | grep -qi "hifiberry"; then
  CARD=$(echo "$APLAY_OUT" | grep -i hifiberry | grep -o 'card [0-9]*' | grep -o '[0-9]*' | head -1)
  if [ "$CARD" = "0" ]; then
    pass "HiFiBerry detected at card 0"
  else
    fail "HiFiBerry detected at card $CARD (expected card 0 — check dtparam=audio=off in config.txt)"
  fi
else
  fail "HiFiBerry not detected — check dtoverlay=hifiberry-amp2 in config.txt"
fi

echo ""

# -----------------------------------------------------------------------------
# 4. pigpiod
# -----------------------------------------------------------------------------
echo "[4/6] pigpiod"

if pigs t &>/dev/null; then
  pass "pigpiod running and responding"
else
  fail "pigpiod not responding — try: sudo systemctl start pigpiod"
fi

echo ""

# -----------------------------------------------------------------------------
# 5. SPI
# -----------------------------------------------------------------------------
echo "[5/6] SPI"

if [ -e /dev/spidev0.0 ]; then
  pass "/dev/spidev0.0 exists"
else
  fail "/dev/spidev0.0 not found — check dtparam=spi=on in config.txt"
fi

echo ""

# -----------------------------------------------------------------------------
# 6. Python packages
# -----------------------------------------------------------------------------
echo "[6/6] Python packages"

python3 - "$LOG" << 'PYEOF'
import sys

log_file = sys.argv[1]
packages = [
    "numpy",
    "scipy",
    "ephem",
    "pyaudio",
    "pigpio",
    "RPi.GPIO",
    "smbus2",
    "hx711",
    "serial",
]

with open(log_file, 'a') as log:
    for module in packages:
        try:
            __import__(module)
            print("  [PASS] %s" % module)
            log.write("PASS\n")
        except Exception as e:
            print("  [FAIL] %s — %s (%s)" % (module, type(e).__name__, e))
            log.write("FAIL\n")
PYEOF

echo ""

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
PASS=$(grep -c "^PASS$" "$LOG" || true)
FAIL=$(grep -c "^FAIL$" "$LOG" || true)
TOTAL=$((PASS + FAIL))

echo "=== Results: $PASS/$TOTAL checks passed ==="
echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "  All checks passed. Ready for panel test:"
  echo "  python3 /home/bird/pyoperant/scripts/test_panel.py"
  echo ""
  exit 0
else
  echo "  $FAIL check(s) failed. Resolve before running panel test."
  echo "  Check /boot/firmware/config.txt for overlay issues."
  echo ""
  exit 1
fi
