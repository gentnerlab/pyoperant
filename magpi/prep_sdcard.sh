#!/bin/bash
# =============================================================================
# prep_sdcard.sh  (run on your Mac after flashing)
# Copies all MagPi files to the SD card bootfs and sets up static IP.
#
# Approach: write NM connection file + a one-shot systemd service to bootfs.
# Inject into firstrun.sh: install + enable the service (no NM needed).
# On next boot the service runs after NM is up, installs the connection,
# reloads NM, then disables itself.
#
# Usage:
#   ./prep_sdcard.sh [bootfs_mount_point]
#
# Default mount point is /Volumes/bootfs
# =============================================================================

set -e

# Prevent macOS from creating ._* AppleDouble sidecar files when copying onto
# the FAT32 bootfs partition below (it can't store Unix permissions/xattrs,
# so cp/tar would otherwise stash them in shadow files that confuse *.deb
# globs and git on the other end).
export COPYFILE_DISABLE=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOOTFS="${1:-/Volumes/bootfs}"

# -----------------------------------------------------------------------------
# Verify SD card is mounted
# -----------------------------------------------------------------------------
if [ ! -d "$BOOTFS" ]; then
  echo "ERROR: $BOOTFS not found."
  echo "Insert the SD card and wait for it to mount, then try again."
  echo "Usage: $0 [mount_point]   (default: /Volumes/bootfs)"
  exit 1
fi

if [ ! -f "$BOOTFS/config.txt" ]; then
  echo "ERROR: $BOOTFS doesn't look like a Pi bootfs (no config.txt found)."
  exit 1
fi

echo "=== MagPi SD card prep ==="
echo "Target: $BOOTFS"
echo ""

# -----------------------------------------------------------------------------
# 1. Copy magpi_packages/
# -----------------------------------------------------------------------------
echo "[1/6] Copying magpi_packages/..."
if [ ! -d "$SCRIPT_DIR/magpi_packages" ]; then
  echo "ERROR: magpi_packages/ not found next to this script."
  echo "Run download_packages.sh first."
  exit 1
fi
if [ ! -f "$SCRIPT_DIR/magpi_packages/keys/id_client_fleet" ]; then
  echo "ERROR: magpi_packages/keys/id_client_fleet not found."
  echo "This board can't clone pyoperant/glab_behaviors from magpi.ucsd.edu"
  echo "on first boot without it. Re-run download_packages.sh (it checks for"
  echo "this key and prints setup instructions if it's missing)."
  exit 1
fi
mkdir -p "$BOOTFS/magpi_packages"
cp -r "$SCRIPT_DIR/magpi_packages/deb" "$BOOTFS/magpi_packages/"
cp -r "$SCRIPT_DIR/magpi_packages/pip" "$BOOTFS/magpi_packages/"
mkdir -p "$BOOTFS/magpi_packages/keys"
cp "$SCRIPT_DIR/magpi_packages/keys/id_client_fleet" "$BOOTFS/magpi_packages/keys/"
echo "  -> magpi_packages/ copied (deb, pip, client-fleet key)"

# -----------------------------------------------------------------------------
# 2. Copy setup and test scripts
# -----------------------------------------------------------------------------
echo "[2/6] Copying setup and test scripts..."
cp "$SCRIPT_DIR/magpi_revd_setup.sh" "$BOOTFS/"
chmod +x "$BOOTFS/magpi_revd_setup.sh"
echo "  -> magpi_revd_setup.sh copied"
cp "$SCRIPT_DIR/magpi_hardware_test.sh" "$BOOTFS/"
chmod +x "$BOOTFS/magpi_hardware_test.sh"
echo "  -> magpi_hardware_test.sh copied"

# -----------------------------------------------------------------------------
# 3. Write NM connection file to bootfs
# -----------------------------------------------------------------------------
echo "[3/6] Writing eth0-static.nmconnection to bootfs..."

cat > "$BOOTFS/eth0-static.nmconnection" << 'EOF'
[connection]
id=eth0-static
type=ethernet
interface-name=eth0
autoconnect=true

[ipv4]
method=manual
addresses=192.168.1.254/24
gateway=192.168.1.100
dns=8.8.8.8;8.8.4.4;

[ipv6]
method=ignore
EOF

echo "  -> eth0-static.nmconnection written"

# -----------------------------------------------------------------------------
# 4. Write one-shot systemd service to bootfs
#    Runs after NM is up, installs connection file, reloads NM, then
#    disables itself so it only ever runs once.
# -----------------------------------------------------------------------------
echo "[4/6] Writing magpi-network.service to bootfs..."

cat > "$BOOTFS/magpi-network.service" << 'EOF'
[Unit]
Description=MagPi static IP configuration (runs once)
After=NetworkManager.service
Wants=NetworkManager.service
ConditionPathExists=!/etc/NetworkManager/system-connections/eth0-static.nmconnection

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c '\
  mkdir -p /etc/NetworkManager/system-connections && \
  cp /boot/firmware/eth0-static.nmconnection /etc/NetworkManager/system-connections/ && \
  chmod 600 /etc/NetworkManager/system-connections/eth0-static.nmconnection && \
  nmcli con reload && \
  nmcli con up eth0-static || true'
ExecStartPost=/bin/systemctl disable magpi-network.service

[Install]
WantedBy=multi-user.target
EOF

echo "  -> magpi-network.service written"

# -----------------------------------------------------------------------------
# 5. Inject service install + logging into Imager's firstrun.sh
# -----------------------------------------------------------------------------
echo "[5/6] Injecting service install into firstrun.sh..."

IMAGER_FIRSTRUN="$BOOTFS/firstrun.sh"

if [ ! -f "$IMAGER_FIRSTRUN" ]; then
  echo "  WARNING: Imager firstrun.sh not found."
  echo "  Did you apply OS customization settings in Raspberry Pi Imager?"
  echo "  Re-flash with customization enabled (username: bird, SSH: on)."
  exit 1
fi

if grep -q "magpi-network" "$IMAGER_FIRSTRUN"; then
  echo "  -> already injected, skipping"
else
  python3 - "$IMAGER_FIRSTRUN" << 'PYEOF'
import sys
path = sys.argv[1]
block = """
# --- MagPi network service ---
exec >> /var/log/magpi-firstrun.log 2>&1
echo "=== MagPi firstrun: $(date) ==="
echo "Copying magpi-network.service:"
cp /boot/firmware/magpi-network.service /etc/systemd/system/ && echo "  cp OK" || echo "  cp FAILED"
echo "Enabling magpi-network.service:"
systemctl enable magpi-network.service && echo "  enable OK" || echo "  enable FAILED"
echo "=== done ==="
# --- end MagPi network service ---
"""
content = open(path).read()
# Inject BEFORE 'rm -f /boot/firstrun.sh' — dash reads scripts sequentially
# and can't read past the point where the file is deleted.
if 'rm -f /boot/firstrun.sh' in content:
    content = content.replace('rm -f /boot/firstrun.sh', block + 'rm -f /boot/firstrun.sh', 1)
else:
    content = content.rstrip('\n') + '\n' + block + '\nexit 0\n'
open(path, 'w').write(content)
PYEOF
  echo "  -> injected into firstrun.sh"
fi

# -----------------------------------------------------------------------------
# 6. Verify card contents before ejecting
# -----------------------------------------------------------------------------
echo ""
echo "[6/6] Verifying card contents..."
echo ""

MISSING=0

for f in magpi-network.service eth0-static.nmconnection magpi_revd_setup.sh magpi_hardware_test.sh; do
  if [ -f "$BOOTFS/$f" ]; then
    echo "  OK  $f"
  else
    echo "  MISSING  $f"
    MISSING=1
  fi
done

if [ -d "$BOOTFS/magpi_packages" ]; then
  echo "  OK  magpi_packages/"
else
  echo "  MISSING  magpi_packages/"
  MISSING=1
fi

if [ -f "$BOOTFS/magpi_packages/keys/id_client_fleet" ]; then
  echo "  OK  magpi_packages/keys/id_client_fleet"
else
  echo "  MISSING  magpi_packages/keys/id_client_fleet"
  MISSING=1
fi

echo ""
echo "  firstrun.sh injection:"
grep -A3 "magpi-network" "$BOOTFS/firstrun.sh" | sed 's/^/    /'

if [ $MISSING -eq 1 ]; then
  echo ""
  echo "WARNING: some files are missing — do not boot yet, re-run this script."
  exit 1
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo ""
echo "=== SD card ready ==="
echo ""
echo "Next steps:"
echo "  1. Eject:      diskutil eject $BOOTFS"
echo "  2. Boot Pi — wait ~2 min for firstrun + network service"
echo "  3. SSH in:     ssh bird@192.168.1.254"
echo "  4. Check log:  cat /var/log/magpi-firstrun.log"
echo "  5. Run setup:  sudo /boot/firmware/magpi_revd_setup.sh"
