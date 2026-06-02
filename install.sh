#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${VOID_MAP_REPO_URL:-https://github.com/nephorion/void_map.git}"
INSTALL_DIR="${VOID_MAP_INSTALL_DIR:-$HOME/void_map}"

if ! command -v sudo >/dev/null 2>&1; then
  printf '%s\n' 'ERROR: This script requires sudo access to install system packages.' >&2
  exit 1
fi

sudo apt-get update -qq
sudo apt-get install -y python3 python3-dev curl sqlite3 git

if [ ! -f pyproject.toml ]; then
  if [ -d "$INSTALL_DIR/.git" ]; then
    printf '%s\n' "Using existing checkout at $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only || true
  elif [ -e "$INSTALL_DIR" ]; then
    printf '%s\n' "ERROR: $INSTALL_DIR exists but is not a git checkout." >&2
    printf '%s\n' 'Set VOID_MAP_INSTALL_DIR to a different path or move the existing directory.' >&2
    exit 1
  else
    printf '%s\n' "Cloning void_map into $INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
  cd "$INSTALL_DIR"
fi

PROJECT_DIR="$(pwd)"

python_version="$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
)"
if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 8) else 1)
PY
then
  printf 'ERROR: Python 3.8+ is required. Found: %s.\n' "$python_version" >&2
  printf '%s\n' 'On Ubuntu 20.04 you may need to install python3.10 manually.' >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
source "$HOME/.cargo/env" 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1 || ! uv --version >/dev/null 2>&1; then
  printf '%s\n' 'ERROR: uv installation failed. Try installing manually:' >&2
  printf '%s\n' '  curl -LsSf https://astral.sh/uv/install.sh | sh' >&2
  printf '%s\n' 'Then re-run install.sh.' >&2
  exit 1
fi

if [ "$(uname -m)" = "x86_64" ] || [ "$(uname -m)" = "amd64" ]; then
  if ! command -v cloudflared >/dev/null 2>&1; then
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
    sudo dpkg -i /tmp/cloudflared.deb || true
  fi
  if ! command -v cloudflared >/dev/null 2>&1 || ! cloudflared --version >/dev/null 2>&1; then
    printf '%s\n' 'WARNING: cloudflared auto-install only supports amd64.'
    printf '%s\n' 'dev.sh will not work. Download cloudflared manually from:'
    printf '%s\n' '  https://github.com/cloudflare/cloudflared/releases'
  fi
else
  printf '%s\n' 'WARNING: cloudflared auto-install only supports amd64.'
  printf '%s\n' 'dev.sh will not work. Download cloudflared manually from:'
  printf '%s\n' '  https://github.com/cloudflare/cloudflared/releases'
fi

uv sync
chmod +x run.sh dev.sh

printf '%s\n\n' 'void_map installed successfully.'
printf '%s\n' 'To start:'
printf '  cd %s && ./run.sh\n\n' "$PROJECT_DIR"
printf '%s\n' 'To start in dev mode (Cloudflare tunnel for testing on other devices):'
printf '  cd %s && ./dev.sh\n\n' "$PROJECT_DIR"
printf '%s\n' 'To verify a kismetdb has GPS data:'
printf '%s\n' '  sqlite3 your.kismetdb "SELECT COUNT(*) FROM packets WHERE lat != 0 AND lon != 0;"'
