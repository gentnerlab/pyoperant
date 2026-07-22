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
KEYS_DIR="$OUTPUT_DIR/keys"
DOCKER_IMAGE="magpi-builder:bookworm"

echo "=== MagPi package downloader ==="
echo "Output: $OUTPUT_DIR"
echo ""

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "ERROR: Docker is not running. Start Docker Desktop and try again."
  exit 1
fi

# pyoperant and glab_behaviors are no longer bundled here -- magpi_revd_setup.sh
# clones them live from magpi.ucsd.edu during first boot instead (so a fix on
# master is picked up by every board flashed after that point, and the repos
# on the board are real, working git clones pointed at a remote the board can
# actually reach -- see the "CLIENT-FLEET SSH KEY" check below for why this
# needs a key that must already exist before this script can finish).
if [ ! -f "$KEYS_DIR/id_client_fleet" ]; then
  echo "ERROR: $KEYS_DIR/id_client_fleet not found."
  echo "This is the shared private key every Rev D board uses to git-clone"
  echo "from magpi.ucsd.edu during first boot. Generate it once with:"
  echo ""
  echo "  mkdir -p $KEYS_DIR"
  echo "  ssh-keygen -t ed25519 -f $KEYS_DIR/id_client_fleet -N \"\" -C magpi-client-fleet"
  echo ""
  echo "Then add $KEYS_DIR/id_client_fleet.pub to bird@192.168.1.100's"
  echo "~/.ssh/authorized_keys (one-time, on the server) before flashing any boards."
  exit 1
fi

mkdir -p "$DEB_DIR" "$PIP_DIR"

# -----------------------------------------------------------------------------
# 0. Build (or reuse) a cached ARM Docker image with RPi repo pre-configured
#    This saves ~3 min on re-runs by skipping apt-get update/install each time
# -----------------------------------------------------------------------------
echo "[0/3] Preparing ARM build environment..."

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
echo "[1/3] Downloading .deb packages (ARM armhf)..."

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
echo "[2/3] Building Python wheels (ARM armhf)..."

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
echo "[3/3] Smoke-testing pip wheel installation (ARM armhf)..."

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
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Download complete ==="
echo ""
echo "Contents of $OUTPUT_DIR:"
echo "  deb/  : $(ls "$DEB_DIR" | wc -l) packages"
echo "  pip/  : $(ls "$PIP_DIR" | wc -l) wheels"
echo "  keys/ : client-fleet SSH key (for live-cloning repos from magpi.ucsd.edu on first boot)"
echo ""
echo "pyoperant and glab_behaviors are NOT bundled here -- magpi_revd_setup.sh"
echo "clones them live from magpi.ucsd.edu during first boot instead."
echo ""
echo "To force a full refresh of any section:"
echo "  rm -rf $DEB_DIR   # re-download .deb packages"
echo "  rm -rf $PIP_DIR   # rebuild pip wheels"
echo "  docker rmi $DOCKER_IMAGE  # rebuild Docker image"
echo ""
echo "Next steps:"
echo "  1. Flash SD card with Raspberry Pi Imager (Bookworm Lite 32-bit)"
echo "     - Set username: bird"
echo "     - Enable SSH (password auth)"
echo "  2. Insert SD card — bootfs volume will appear in Finder"
echo "  3. Run:  ./prep_sdcard.sh"
