#!/bin/bash
# =============================================================================
# download_packages.sh  (run on your Mac)
# Downloads all packages required for the MagPi Rev D base image.
# Requires Docker Desktop to be running.
# Output goes into magpi/magpi_packages/ — copy this folder to the Pi SD card.
#
# Re-run anytime to refresh packages. Already-downloaded items are skipped.
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/magpi_packages"
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
echo "[0/6] Preparing ARM build environment..."

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
#    Skip only if every currently-listed package already has a matching
#    .deb file -- a blanket "any debs present -> skip" check would silently
#    never fetch a package added to DEB_PACKAGES after deb/ was first
#    populated (force refresh: rm -rf magpi_packages/deb/).
# -----------------------------------------------------------------------------
echo "[1/6] Downloading .deb packages (ARM armhf)..."

DEB_PACKAGES=(
  python3-pip
  i2c-tools
  python3-smbus
  pigpio
  python3-pigpio
  git
  libasound2-dev
  postfix
  python3-setuptools
  python3-wheel
  python3-numpy
  python3-scipy
  python3-pyaudio
  python3-serial
  python3-pandas
)

MISSING_DEB_PACKAGES=()
for pkg in "${DEB_PACKAGES[@]}"; do
  if ls "$DEB_DIR"/${pkg}_* > /dev/null 2>&1; then
    :
  else
    MISSING_DEB_PACKAGES+=("$pkg")
  fi
done

if [ ${#MISSING_DEB_PACKAGES[@]} -eq 0 ] && [ "$(ls "$DEB_DIR"/*.deb 2>/dev/null | wc -l)" -gt 0 ]; then
  echo "  -> $(ls "$DEB_DIR"/*.deb | wc -l) .deb files already present, skipping"
  echo "     (to refresh: rm -rf $DEB_DIR && re-run)"
else
  echo "  -> missing: ${MISSING_DEB_PACKAGES[*]}"
  docker run --rm \
    --platform linux/arm/v7 \
    -v "$DEB_DIR":/output \
    -e DEBIAN_FRONTEND=noninteractive \
    -e DEB_PACKAGES="${DEB_PACKAGES[*]}" \
    "$DOCKER_IMAGE" \
    bash -c '
      set -e
      apt-get install -y -d --no-install-recommends $DEB_PACKAGES
      cp /var/cache/apt/archives/*.deb /output/ 2>/dev/null || true
      # Force-download packages that may already be installed in the build
      # container (apt-get install -d skips them, apt-get download always fetches)
      cd /output && apt-get download \
        python3-setuptools \
        python3-wheel
      echo "Done: $(ls /output/*.deb | wc -l) .deb files downloaded"
    '
  echo "  -> $(ls "$DEB_DIR"/*.deb | wc -l) .deb files saved to $DEB_DIR"
fi

# -----------------------------------------------------------------------------
# 2. Build Python wheels (ARM armhf, compiled inside Docker)
#    ephem and RPi.GPIO need C compilation — build them here so the Pi can
#    install pre-built wheels without needing python3-dev headers.
#    Skip individual packages if their wheel already exists.
# -----------------------------------------------------------------------------
echo "[2/6] Building Python wheels (ARM armhf)..."

PACKAGES=(
  setuptools
  ephem
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
  echo "  -> Building: ${MISSING_PACKAGES[*]}"
  docker run --rm \
    --platform linux/arm/v7 \
    -v "$PIP_DIR":/output \
    -e DEBIAN_FRONTEND=noninteractive \
    "$DOCKER_IMAGE" \
    bash -c "
      set -e
      pip3 wheel \
        --wheel-dir /output \
        --no-deps \
        ${MISSING_PACKAGES[*]}
      echo \"Done: \$(ls /output | wc -l) wheels in output\"
    "
  echo "  -> $(ls "$PIP_DIR" | wc -l) wheels in $PIP_DIR"
else
  echo "  -> all wheels already present"
fi

# -----------------------------------------------------------------------------
# 3. Smoke-test: verify pip wheels install cleanly in a fresh ARM container
#    Catches missing transitive deps (e.g. Adafruit-Blinka) before the Pi does.
#    Uses --no-index so only our bundled wheels are available — if any dep is
#    missing the install fails here, not on the bench.
# -----------------------------------------------------------------------------
echo "[3/6] Smoke-testing pip wheel installation (ARM armhf)..."

docker run --rm \
  --platform linux/arm/v7 \
  -v "$PIP_DIR":/wheels \
  "$DOCKER_IMAGE" \
  bash -c '
    set -e
    echo "  Installing from local wheels only..."
    pip3 install --quiet \
      --break-system-packages \
      --no-index \
      --find-links=/wheels \
      ephem RPi.GPIO hx711 smbus2

    echo "  Testing imports..."
    python3 -c "
import sys, importlib
ok = True
tests = [
    (\"ephem\",    \"ephem\"),
    (\"smbus2\",   \"smbus2\"),
    (\"hx711\",    \"hx711\"),
    (\"RPi.GPIO\", \"RPi.GPIO\"),
]
for pkg, mod in tests:
    try:
        importlib.import_module(mod)
        print(\"    \" + pkg + \": OK\")
    except RuntimeError as e:
        # Hardware not present in Docker — import structure is fine
        print(\"    \" + pkg + \": OK (no hardware: \" + str(e) + \")\")
    except Exception as e:
        print(\"    \" + pkg + \": FAIL — \" + str(e))
        ok = False
sys.exit(0 if ok else 1)
"
  ' || {
    echo ""
    echo "ERROR: Smoke test failed — fix package list before flashing SD cards."
    exit 1
  }

echo "  -> Smoke test passed"

# -----------------------------------------------------------------------------
# 4. Clone git repositories
# -----------------------------------------------------------------------------
echo "[4/6] Cloning git repositories..."

# pyoperant (public) — python3-migration branch
# TODO: once python3-migration is merged into main, remove --branch flag and
#       the fetch/checkout lines below so this clones the default branch.
if [ ! -d "$REPOS_DIR/pyoperant" ]; then
  git clone --branch python3-migration git@github.com:gentnerlab/pyoperant.git "$REPOS_DIR/pyoperant"
  echo "  -> pyoperant cloned (python3-migration branch)"
else
  echo "  -> pyoperant already exists, pulling latest..."
  git -C "$REPOS_DIR/pyoperant" fetch
  # Reset hard so local patches (applied below) don't block the pull
  git -C "$REPOS_DIR/pyoperant" reset --hard origin/python3-migration
  echo "  -> pyoperant updated to $(git -C "$REPOS_DIR/pyoperant" rev-parse --short HEAD)"
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
# 5. Package repos as a tarball
#    bootfs (the SD card partition prep_sdcard.sh writes to) is FAT32 — it
#    can't store Unix permissions, symlinks, or git's packed object files.
#    Copying the raw repos/ tree onto it (and later off it, onto the Pi's
#    home directory) silently mangles executable bits, turns symlinks into
#    regular files, and corrupts the git pack index via AppleDouble ._ sidecar
#    files. Tar first so the payload crosses FAT32 as one opaque file.
# -----------------------------------------------------------------------------
echo "[5/6] Packaging repos for FAT32-safe transfer..."
COPYFILE_DISABLE=1 tar -czf "$OUTPUT_DIR/repos.tar.gz" -C "$REPOS_DIR" .
echo "  -> repos.tar.gz created ($(du -h "$OUTPUT_DIR/repos.tar.gz" | cut -f1))"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Download complete ==="
echo ""
echo "Contents of $OUTPUT_DIR:"
echo "  deb/        : $(ls "$DEB_DIR" | wc -l) packages"
echo "  pip/        : $(ls "$PIP_DIR" | wc -l) wheels"
echo "  repos.tar.gz: pyoperant, glab_behaviors (tarred for FAT32-safe transfer)"
echo ""
echo "To force a full refresh of any section:"
echo "  rm -rf $DEB_DIR   # re-download .deb packages"
echo "  rm -rf $PIP_DIR   # rebuild pip wheels"
echo "  rm -rf $REPOS_DIR # re-clone repos"
echo "  docker rmi $DOCKER_IMAGE  # rebuild Docker image"
echo ""
echo "Next steps:"
echo "  1. Flash SD card with Raspberry Pi Imager (Bookworm Lite 32-bit)"
echo "     - Set username: bird"
echo "     - Enable SSH (password auth)"
echo "  2. Insert SD card — bootfs volume will appear in Finder"
echo "  3. Run:  ./prep_sdcard.sh"
