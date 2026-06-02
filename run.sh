#!/usr/bin/env bash
set -euo pipefail

port="${VOID_MAP_PORT:-5000}"
url="http://localhost:$port"
printf '%s\n' "void_map running at $url"

if command -v xdg-open >/dev/null 2>&1; then
  (sleep 1; xdg-open "$url" >/dev/null 2>&1 || printf '%s\n' "Open $url in your browser.") &
else
  printf '%s\n' "Open $url in your browser."
fi

VOID_MAP_PORT="$port" uv run python backend/app.py
