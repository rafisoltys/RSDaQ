#!/usr/bin/env bash
# Install RSDaQ on a fresh Raspberry Pi 5 (Bookworm).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ">> Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
  build-essential git cmake \
  python3 python3-venv python3-pip python3-dev \
  libhdf5-dev \
  libxcb-cursor0 libxkbcommon-x11-0

echo ">> Building Digilent daqhats library..."
if [ ! -d "/tmp/daqhats" ]; then
  git clone https://github.com/mccdaq/daqhats.git /tmp/daqhats
fi
pushd /tmp/daqhats >/dev/null
sudo ./install.sh
popd >/dev/null

echo ">> Creating Python virtual environment..."
python3 -m venv "$REPO_DIR/.venv" --system-site-packages
# shellcheck disable=SC1091
source "$REPO_DIR/.venv/bin/activate"

echo ">> Installing Python requirements..."
pip install --upgrade pip
pip install -r "$REPO_DIR/requirements.txt"

echo
echo "Done. Detected boards:"
daqhats_list_boards || true
echo
echo "Run RSDaQ with:  ./scripts/run.sh"
