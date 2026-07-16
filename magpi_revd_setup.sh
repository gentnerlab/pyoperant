#!/bin/bash
# =============================================================================
# magpi_revd_setup.sh
# First-boot setup script for MagPi Rev D boards (Raspberry Pi 3B+)
# Tested against Raspberry Pi OS Bookworm Lite (32-bit)
# Run once as root after first boot: sudo /boot/firmware/magpi_revd_setup.sh
# =============================================================================

set -e
LOG=/var/log/magpi_setup.log
exec > >(tee -a "$LOG") 2>&1
echo "=== MagPi Rev D setup started: $(date) ==="

# On Bookworm, bootfs is mounted at /boot/firmware
BOOT=/boot/firmware
PACKAGES_DIR=$BOOT/magpi_packages
MAGPI_USER=bird
HOME_DIR=/home/$MAGPI_USER
export DEBIAN_FRONTEND=noninteractive

# Verify packages directory exists
if [ ! -d "$PACKAGES_DIR" ]; then
  echo "ERROR: $PACKAGES_DIR not found."
  echo "Copy magpi_packages/ to the bootfs partition and try again."
  exit 1
fi

# Verify user exists
if [ ! -d "$HOME_DIR" ]; then
  echo "ERROR: Home directory $HOME_DIR not found."
  echo "Check that the default user is set to 'bird' in Raspberry Pi Imager."
  exit 1
fi

# -----------------------------------------------------------------------------
# INTERACTIVE CONFIGURATION
# -----------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  MagPi Rev D Board Configuration"
echo "============================================"
echo ""

# Hostname
read -p "Enter hostname [magpi00]: " INPUT_HOSTNAME
HOSTNAME=${INPUT_HOSTNAME:-magpi00}

# IP Address
read -p "Enter static IP address [192.168.1.1]: " INPUT_IP
IP_ADDRESS=${INPUT_IP:-192.168.1.1}

# Gateway
read -p "Enter gateway [192.168.1.100]: " INPUT_GW
GATEWAY=${INPUT_GW:-192.168.1.100}

# Confirm
echo ""
echo "--------------------------------------------"
echo "  Hostname : $HOSTNAME"
echo "  IP       : $IP_ADDRESS/24"
echo "  Gateway  : $GATEWAY"
echo "--------------------------------------------"
read -p "Proceed with these settings? [Y/n]: " CONFIRM
CONFIRM=${CONFIRM:-Y}

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Aborted — no changes made."
  exit 0
fi

echo ""

# -----------------------------------------------------------------------------
# 1. HOSTNAME
# -----------------------------------------------------------------------------
echo "[1/9] Setting hostname..."

hostnamectl set-hostname "$HOSTNAME"
sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME/" /etc/hosts
echo "  -> hostname set to $HOSTNAME"

# -----------------------------------------------------------------------------
# 2. STATIC IP (Bookworm uses NetworkManager / nmcli)
# -----------------------------------------------------------------------------
echo "[2/9] Configuring static IP..."

nmcli con delete eth0-static 2>/dev/null || true

nmcli con add type ethernet \
  ifname eth0 \
  con-name eth0-static \
  ipv4.method manual \
  ipv4.addresses "$IP_ADDRESS/24" \
  ipv4.gateway "$GATEWAY" \
  ipv4.dns "8.8.8.8 8.8.4.4" \
  connection.autoconnect yes

echo "  -> static IP $IP_ADDRESS configured"

# -----------------------------------------------------------------------------
# 3. BOOT CONFIG
# -----------------------------------------------------------------------------
echo "[3/9] Writing /boot/firmware/config.txt..."

# Only add config if not already present
if ! grep -q "MagPi Rev D config" $BOOT/config.txt; then
  cat >> $BOOT/config.txt << 'EOF'

# --- MagPi Rev D config ---

# HiFiBerry AMP2 — disable onboard audio including HDMI audio
dtoverlay=hifiberry-amp2
dtparam=audio=off
dtoverlay=vc4-kms-v3d,noaudio

# I2C for PCA9685 (lights @ 0x55, servo @ 0x45)
dtparam=i2c_arm=on
dtparam=i2c_arm_baudrate=400000

# SPI
dtparam=spi=on

# Headless — return GPU RAM to CPU
gpu_mem=16

# Disable Bluetooth (frees UART, reduces overhead)
dtoverlay=disable-bt

# Disable WiFi (wired-only setup)
dtoverlay=disable-wifi
EOF
  echo "  -> config.txt updated"
else
  echo "  -> config.txt already configured, skipping"
fi

# Enable i2c-dev module (creates /dev/i2c-1)
if ! grep -q "i2c-dev" /etc/modules-load.d/i2c.conf 2>/dev/null; then
  echo "i2c-dev" > /etc/modules-load.d/i2c.conf
  echo "  -> i2c-dev module enabled"
fi

# -----------------------------------------------------------------------------
# 4. DISABLE UNNECESSARY SERVICES
# -----------------------------------------------------------------------------
echo "[4/9] Disabling unnecessary services..."

systemctl disable bluetooth     2>/dev/null || true
systemctl disable hciuart       2>/dev/null || true
systemctl disable avahi-daemon  2>/dev/null || true
systemctl disable triggerhappy  2>/dev/null || true
systemctl disable cups          2>/dev/null || true

# Disable HDMI on boot via systemd (Bookworm has no rc.local by default)
if [ ! -f /etc/systemd/system/disable-hdmi.service ]; then
  cat > /etc/systemd/system/disable-hdmi.service << 'EOF'
[Unit]
Description=Disable HDMI output
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/tvservice -o
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  systemctl enable disable-hdmi 2>/dev/null || true
fi

echo "  -> services disabled"

# -----------------------------------------------------------------------------
# 5. PACKAGE INSTALLATION (offline from SD card)
# -----------------------------------------------------------------------------
echo "[5/9] Installing .deb packages..."

if [ ! -d "$PACKAGES_DIR/deb" ] || [ "$(ls $PACKAGES_DIR/deb/*.deb 2>/dev/null | wc -l)" -eq 0 ]; then
  echo "ERROR: No .deb files found in $PACKAGES_DIR/deb"
  exit 1
fi

# Pre-seed postfix debconf to suppress interactive configuration screen
echo "postfix postfix/main_mailer_type select Satellite system" | debconf-set-selections
echo "postfix postfix/mailname string $HOSTNAME" | debconf-set-selections
echo "postfix postfix/relayhost string [192.168.1.100]" | debconf-set-selections
export DEBIAN_FRONTEND=noninteractive

# Check which packages are already installed and skip them
PACKAGES_TO_INSTALL=()
for deb in "$PACKAGES_DIR"/deb/*.deb; do
  PKG=$(dpkg-deb -f "$deb" Package)
  VER=$(dpkg-deb -f "$deb" Version)
  if dpkg -s "$PKG" &>/dev/null; then
    echo "  -> $PKG already installed, skipping"
  else
    PACKAGES_TO_INSTALL+=("$deb")
  fi
done

if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
  # Two passes to handle dependency ordering
  dpkg -i --force-depends "${PACKAGES_TO_INSTALL[@]}" || true
  dpkg -i --force-depends "${PACKAGES_TO_INSTALL[@]}" || true
  echo "  -> ${#PACKAGES_TO_INSTALL[@]} .deb packages installed"
else
  echo "  -> all packages already installed, skipping"
fi

# Enable and start pigpio daemon
systemctl enable pigpiod
systemctl start pigpiod || true
echo "  -> pigpiod enabled"

# -----------------------------------------------------------------------------
# 6. HIFIBERRY AUDIO CONFIG
# -----------------------------------------------------------------------------
echo "[6/9] Configuring HiFiBerry as default ALSA device..."

# Detect HiFiBerry card number dynamically
HIFI_CARD=$(aplay -l 2>/dev/null | grep -i hifiberry | grep -o 'card [0-9]*' | grep -o '[0-9]*' | head -1)
if [ -z "$HIFI_CARD" ]; then
  echo "WARNING: HiFiBerry not detected — defaulting to card 1 (reboot may be required)"
  HIFI_CARD=1
fi

cat > /etc/asound.conf << EOF
pcm.!default {
  type hw card $HIFI_CARD
}
ctl.!default {
  type hw card $HIFI_CARD
}
EOF
echo "  -> HiFiBerry set as default ALSA device (card $HIFI_CARD)"

# Set Digital volume to 100% (default is muted/low — required for output)
amixer -c "$HIFI_CARD" sset Digital 100% 2>/dev/null && \
  echo "  -> Digital volume set to 100%" || \
  echo "  WARNING: Could not set Digital volume (reboot may be required)"

echo "  -> ALSA configured"

# -----------------------------------------------------------------------------
# 7. PYOPERANT & GLAB_BEHAVIORS (offline from SD card)
# -----------------------------------------------------------------------------
echo "[7/9] Installing pyoperant and glab_behaviors..."

# Clean up any stale egg-links from previous installs
find /usr -name "pyoperant.egg-link" -delete 2>/dev/null || true
rm -rf "$HOME_DIR/pyoperant/pyoperant.egg-info" 2>/dev/null || true
grep -v pyoperant /usr/lib/python3/dist-packages/easy-install.pth > /tmp/easy-install.pth 2>/dev/null && \
  mv /tmp/easy-install.pth /usr/lib/python3/dist-packages/easy-install.pth || true

if [ ! -d "$PACKAGES_DIR/repos/pyoperant" ]; then
  echo "ERROR: pyoperant repo not found in $PACKAGES_DIR/repos/"
  exit 1
fi

# Copy repos to home directory (skip if already installed)
if [ ! -d "$HOME_DIR/pyoperant" ]; then
  cp -r "$PACKAGES_DIR/repos/pyoperant" $HOME_DIR/pyoperant
  chown -R $MAGPI_USER:$MAGPI_USER $HOME_DIR/pyoperant
fi
# setuptools must be importable before pip can do an editable install
pip3 install --break-system-packages --no-index --no-build-isolation \
  --find-links="$PACKAGES_DIR/pip" \
  setuptools
pip3 install --break-system-packages --no-index --no-build-isolation \
  --find-links="$PACKAGES_DIR/pip" \
  -e $HOME_DIR/pyoperant
echo "  -> pyoperant installed"

if [ -d "$PACKAGES_DIR/repos/glab_behaviors" ]; then
  if [ ! -d "$HOME_DIR/glab_behaviors" ]; then
    cp -r "$PACKAGES_DIR/repos/glab_behaviors" $HOME_DIR/glab_behaviors
    chown -R $MAGPI_USER:$MAGPI_USER $HOME_DIR/glab_behaviors
  fi
  # glab_behaviors has no setup.py — add parent dir to Python path via .pth file
  echo "$HOME_DIR" > /usr/lib/python3/dist-packages/glab_behaviors.pth
  # Empty __init__.py — Python 2 style imports cause errors in Python 3
  : > "$HOME_DIR/glab_behaviors/__init__.py"
  # Remove stray email file if present
  rm -f "$HOME_DIR/glab_behaviors/magpi12@ucsd.edu"
  echo "  -> glab_behaviors added to Python path"
else
  echo "WARNING: glab_behaviors not found — skipping"
fi

# Install Python wheels
if [ -d "$PACKAGES_DIR/pip" ] && [ "$(ls $PACKAGES_DIR/pip 2>/dev/null | wc -l)" -gt 0 ]; then
  # Ensure setuptools is available for source builds
  dpkg -i "$PACKAGES_DIR"/deb/python3-setuptools*.deb 2>/dev/null || true
  # numpy installed via python3-numpy .deb in step 5
  pip3 install --break-system-packages --no-index --no-build-isolation \
    --find-links="$PACKAGES_DIR/pip" \
    ephem \
    adafruit-circuitpython-pca9685 \
    adafruit-circuitpython-motor \
    RPi.GPIO \
    hx711 \
    smbus2
  echo "  -> Python wheels installed"
else
  echo "WARNING: No pip wheels found — skipping"
fi

# -----------------------------------------------------------------------------
# 8. POSTFIX — satellite relay through magpi server (192.168.1.100)
# -----------------------------------------------------------------------------
echo "[8/9] Configuring postfix mail relay..."

postconf -e "relayhost = [192.168.1.100]"
postconf -e "inet_interfaces = loopback-only"
postconf -e "mydestination ="
postconf -e "myorigin = /etc/hostname"
postconf -e "myhostname = $HOSTNAME"
postconf -e "smtp_fallback_relay ="

systemctl enable postfix
systemctl restart postfix || true
echo "  -> postfix configured as satellite relay via 192.168.1.100"

# -----------------------------------------------------------------------------
# 9. MAGPI-SPECIFIC CONFIG
# -----------------------------------------------------------------------------
echo "[9/10] Writing MagPi Rev D system files..."


echo 'revd' > /etc/magpi_revision
echo "  -> /etc/magpi_revision set to revd"

mkdir -p $HOME_DIR/opdat
chown $MAGPI_USER:$MAGPI_USER $HOME_DIR/opdat
echo "  -> $HOME_DIR/opdat created"

# -----------------------------------------------------------------------------
# 9. CUSTOM MOTD
# -----------------------------------------------------------------------------
echo "[10/10] Setting MOTD..."

# Write ASCII art with quoted heredoc (no variable expansion, safe for special chars)
cat > /etc/motd << 'EOF'

Welcome to
   ______           __                     __          __
  / ____/__  ____  / /_____  ___  _____   / /   ____ _/ /_
 / / __/ _ \/ __ \/ __/ __ \/ _ \/ ___/  / /   / __ `/ __ \
/ /_/ /  __/ / / / /_/ / / /  __/ /     / /___/ /_/ / /_/ /
\____/\___/_/ /_/\__/_/ /_/\___/_/     /_____/\__,_/_.___/
                 __  ___            ____
                /  |/  /___ _____ _/ __ \(_)
               / /|_/ / __ `/ __ `/ /_/ / /
              / /  / / /_/ / /_/ / ____/ /
             /_/  /_/\__,_/\__, /_/   /_/
                          /____/

RPiOperant Interface
Rev D | Gentner Lab | UCSD
EOF

# Append dynamic hostname and IP (separate echo so variables expand correctly)
echo " Hostname: $HOSTNAME" >> /etc/motd
echo " IP:       $IP_ADDRESS" >> /etc/motd
echo "" >> /etc/motd

# -----------------------------------------------------------------------------
# VERIFY HARDWARE
# -----------------------------------------------------------------------------
echo "=== Hardware verification ==="

echo "--- I2C devices (expect 0x45 and 0x55) ---"
i2cdetect -y 1 || echo "WARNING: reboot required before I2C is active"

echo "--- Audio devices (expect HiFiBerry) ---"
aplay -l || echo "WARNING: reboot required before audio is active"

echo "--- pigpiod ---"
pigs t 2>/dev/null && echo "pigpiod OK" || echo "WARNING: pigpiod not responding"

echo ""
echo "=== MagPi Rev D setup complete: $(date) ==="
echo ">>> REBOOT NOW: sudo reboot <<<"

# Uncomment to self-delete after verified:
# rm -- "$0"
