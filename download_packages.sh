#!/bin/bash
# =============================================================================
# download_packages.sh  (run on your Mac)
# Downloads all packages required for the MagPi Rev D base image.
# Requires Docker Desktop to be running.
# Output goes into ./magpi_packages/ — copy this folder to the Pi SD card.
#
# Re-run anytime to refresh packages. Already-downloaded items are skipped.
# =============================================================================

set -e

OUTPUT_DIR="$(pwd)/magpi_packages"
DEB_DIR="$OUTPUT_DIR/deb"
PIP_DIR="$OUTPUT_DIR/pip"
REPOS_DIR="$OUTPUT_DIR/repos"
TMP_DIR="$OUTPUT_DIR/tmp"
DOCKER_IMAGE="magpi-builder:bookworm"

echo "=== MagPi package downloader ==="
echo "Output: $OUTPUT_DIR"
echo ""

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "ERROR: Docker is not running. Start Docker Desktop and try again."
  exit 1
fi

mkdir -p "$DEB_DIR" "$PIP_DIR" "$REPOS_DIR" "$TMP_DIR"

# -----------------------------------------------------------------------------
# 0. Build (or reuse) a cached ARM Docker image with RPi repo pre-configured
#    This saves ~3 min on re-runs by skipping apt-get update/install each time
# -----------------------------------------------------------------------------
echo "[0/4] Preparing ARM build environment..."

if docker image inspect "$DOCKER_IMAGE" > /dev/null 2>&1; then
  echo "  -> $DOCKER_IMAGE already built, reusing"
else
  echo "  -> Building $DOCKER_IMAGE (one-time setup, ~3-4 min)..."
  docker buildx build \
    --platform linux/arm/v7 \
    --tag "$DOCKER_IMAGE" \
    --load \
    - << 'DOCKERFILE'
FROM debian:bookworm
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && \
    apt-get install -y -q curl gnupg python3-pip python3-dev libpython3-dev gcc && \
    curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key \
      | gpg --dearmor -o /usr/share/keyrings/raspberrypi-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.gpg] http://archive.raspberrypi.com/debian/ bookworm main" \
      > /etc/apt/sources.list.d/raspi.list && \
    apt-get update -qq
DOCKERFILE
  echo "  -> $DOCKER_IMAGE built and cached"
fi

# -----------------------------------------------------------------------------
# 1. Download .deb packages
#    Skip if deb/ already has files (force refresh: rm -rf magpi_packages/deb/)
# -----------------------------------------------------------------------------
echo "[1/4] Downloading .deb packages (ARM armhf)..."

if [ "$(ls "$DEB_DIR"/*.deb 2>/dev/null | wc -l)" -gt 0 ]; then
  echo "  -> $(ls "$DEB_DIR"/*.deb | wc -l) .deb files already present, skipping"
  echo "     (to refresh: rm -rf $DEB_DIR && re-run)"
else
  docker run --rm \
    --platform linux/arm/v7 \
    -v "$DEB_DIR":/output \
    -e DEBIAN_FRONTEND=noninteractive \
    "$DOCKER_IMAGE" \
    bash -c '
      set -e
      apt-get install -y -d --no-install-recommends \
        python3-pip \
        python3-dev \
        i2c-tools \
        python3-smbus \
        pigpio \
        python3-pigpio \
        git \
        libasound2-dev \
        postfix \
        libpython3-dev \
        python3-setuptools \
        python3-wheel \
        python3-numpy
      cp /var/cache/apt/archives/*.deb /output/ 2>/dev/null || true
      # Force-download packages that may already be installed in the build
      # container (apt-get install -d skips them, apt-get download always fetches)
      cd /output && apt-get download \
        python3-setuptools \
        python3-wheel \
        python3-dev \
        libpython3-dev
      echo "Done: $(ls /output/*.deb | wc -l) .deb files downloaded"
    '
  echo "  -> $(ls "$DEB_DIR"/*.deb | wc -l) .deb files saved to $DEB_DIR"
fi

# -----------------------------------------------------------------------------
# 2. Download Python wheels
#    Skip individual packages if their wheel/tarball already exists
# -----------------------------------------------------------------------------
echo "[2/4] Downloading Python wheels (ARM armhf)..."

PACKAGES=(
  setuptools
  ephem
  adafruit-circuitpython-pca9685
  adafruit-circuitpython-motor
  RPi.GPIO
  hx711
  smbus2
)
# numpy is installed via python3-numpy .deb (faster, avoids armhf wheel issues)

# Check which packages are missing
MISSING_PACKAGES=()
for pkg in "${PACKAGES[@]}"; do
  pkg_lower=$(echo "$pkg" | tr '[:upper:]' '[:lower:]' | tr '-' '_')
  if ls "$PIP_DIR"/${pkg_lower}* "$PIP_DIR"/${pkg}* 2>/dev/null | head -1 | grep -q .; then
    echo "  -> $pkg already downloaded, skipping"
  else
    MISSING_PACKAGES+=("$pkg")
  fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
  echo "  -> Downloading: ${MISSING_PACKAGES[*]}"
  docker run --rm \
    --platform linux/arm/v7 \
    -v "$PIP_DIR":/output \
    -e DEBIAN_FRONTEND=noninteractive \
    "$DOCKER_IMAGE" \
    bash -c "
      set -e
      pip3 download \
        --dest /output \
        --prefer-binary \
        --no-deps \
        ${MISSING_PACKAGES[*]}
      echo \"Done: \$(ls /output | wc -l) files in output\"
    "
  echo "  -> $(ls "$PIP_DIR" | wc -l) wheels/tarballs in $PIP_DIR"
else
  echo "  -> all wheels already present"
fi

# -----------------------------------------------------------------------------
# 3. Clone git repositories
# -----------------------------------------------------------------------------
echo "[3/4] Cloning git repositories..."

# pyoperant (public) — python3-migration branch
# TODO: once python3-migration is merged into main, remove --branch flag and
#       the fetch/checkout lines below so this clones the default branch.
if [ ! -d "$REPOS_DIR/pyoperant" ]; then
  git clone --branch python3-migration git@github.com:gentnerlab/pyoperant.git "$REPOS_DIR/pyoperant"
  echo "  -> pyoperant cloned (python3-migration branch)"
else
  echo "  -> pyoperant already exists, pulling latest..."
  git -C "$REPOS_DIR/pyoperant" fetch
  git -C "$REPOS_DIR/pyoperant" checkout python3-migration
  git -C "$REPOS_DIR/pyoperant" pull
fi

# py-behaviors (private) — clone to tmp, extract glab_behaviors subfolder
if [ ! -d "$REPOS_DIR/glab_behaviors" ]; then
  echo "  -> Cloning py-behaviors (private repo, requires SSH key)..."
  git clone git@github.com:gentnerlab/py-behaviors.git "$TMP_DIR/py-behaviors"
  if [ -d "$TMP_DIR/py-behaviors/glab_behaviors" ]; then
    cp -r "$TMP_DIR/py-behaviors/glab_behaviors" "$REPOS_DIR/glab_behaviors"
    echo "  -> glab_behaviors extracted from py-behaviors"
  else
    echo "WARNING: glab_behaviors subfolder not found in py-behaviors — check repo structure"
  fi
  rm -rf "$TMP_DIR/py-behaviors"
else
  echo "  -> glab_behaviors already exists, skipping"
fi

# Patch default email in pyoperant
sed -i '' "s/bradtheilman@gmail\.com/tgentner@ucsd.edu/g" \
  "$REPOS_DIR/pyoperant/pyoperant/local_pi_revd.py" 2>/dev/null && \
  echo "  -> Patched default email in local_pi_revd.py"

# Patch /home/pi -> /home/bird in pyoperant configs
sed -i '' "s|/home/pi/|/home/bird/|g" \
  "$REPOS_DIR/pyoperant/pyoperant/local_pi_revd.py" 2>/dev/null && \
  echo "  -> Patched home directory to /home/bird in local_pi_revd.py"

# Fix glab_behaviors __init__.py for Python 3
sed -i '' 's/^from \([a-zA-Z]\)/from .\1/' \
  "$REPOS_DIR/glab_behaviors/__init__.py" 2>/dev/null && \
  echo "  -> Patched glab_behaviors/__init__.py for Python 3"

# -----------------------------------------------------------------------------
# 4. Write firstrun.sh
# -----------------------------------------------------------------------------
echo "[4/4] Writing firstrun.sh..."

cat > "$OUTPUT_DIR/firstrun.sh" << 'EOF'
#!/bin/bash
# Sets static IP on first boot — runs before magpi_revd_setup.sh
nmcli con add type ethernet \
  ifname eth0 \
  con-name eth0-static \
  ipv4.method manual \
  ipv4.addresses 192.168.1.1/24 \
  ipv4.gateway 192.168.1.100 \
  ipv4.dns "8.8.8.8 8.8.4.4" \
  connection.autoconnect yes
EOF

chmod +x "$OUTPUT_DIR/firstrun.sh"
echo "  -> firstrun.sh created"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Download complete ==="
echo ""
echo "Contents of $OUTPUT_DIR:"
echo "  deb/        : $(ls "$DEB_DIR" | wc -l) packages"
echo "  pip/        : $(ls "$PIP_DIR" | wc -l) wheels/tarballs"
echo "  repos/      : pyoperant, glab_behaviors"
echo ""
echo "To force a full refresh of any section:"
echo "  rm -rf $DEB_DIR   # re-download .deb packages"
echo "  rm -rf $PIP_DIR   # re-download pip wheels"
echo "  rm -rf $REPOS_DIR # re-clone repos"
echo "  docker rmi $DOCKER_IMAGE  # rebuild Docker image"
echo ""
echo "Next steps:"
echo "  1. Flash SD card with Raspberry Pi Imager (Bookworm Lite 32-bit)"
echo "     - Set username: bird"
echo "     - Enable SSH (password auth)"
echo "  2. Insert SD card — bootfs volume will appear in Finder"
echo "  3. Run:  ./prep_sdcard.sh"
echo "  4. Eject SD card, insert into Pi, power on"
echo "  5. Wait ~2 min for firstrun + network service to run"
echo "  6. SSH in:  ssh bird@192.168.1.1"
echo "  7. Run:  sudo /boot/firmware/magpi_revd_setup.sh"
