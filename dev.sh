#!/usr/bin/env bash
set -euo pipefail

if ! command -v cloudflared >/dev/null 2>&1; then
  printf '%s\n' 'ERROR: cloudflared is not installed.' >&2
  printf '%s\n' 'Install it from https://github.com/cloudflare/cloudflared/releases or re-run ./install.sh on amd64 Linux.' >&2
  exit 1
fi

tmp_log="$(mktemp)"
flask_pid=""
cloudflared_pid=""
port="${VOID_MAP_PORT:-}"

cleanup() {
  [ -n "$cloudflared_pid" ] && kill "$cloudflared_pid" >/dev/null 2>&1 || true
  [ -n "$flask_pid" ] && kill "$flask_pid" >/dev/null 2>&1 || true
  rm -f "$tmp_log"
}
trap cleanup EXIT INT TERM

if [ -z "$port" ]; then
  port="$(uv run python - <<'PY'
import socket
for candidate in range(5000, 5021):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("127.0.0.1", candidate)) != 0:
            print(candidate)
            raise SystemExit(0)
raise SystemExit("No free port found in 5000-5020")
PY
)"
fi

VOID_MAP_PORT="$port" uv run python backend/app.py >/tmp/void_map_flask.log 2>&1 &
flask_pid="$!"

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$port/api/health" 2>/dev/null | grep -q '"app":"void_map"'; then
    break
  fi
  if ! kill -0 "$flask_pid" >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: Flask failed to start. See /tmp/void_map_flask.log for details.' >&2
    exit 1
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:$port/api/health" 2>/dev/null | grep -q '"app":"void_map"'; then
  printf '%s\n' "ERROR: void_map did not start on port $port." >&2
  printf '%s\n' 'See /tmp/void_map_flask.log for details.' >&2
  exit 1
fi

cloudflared tunnel --url "http://localhost:$port" 2>"$tmp_log" &
cloudflared_pid="$!"

public_url=""
for _ in $(seq 1 60); do
  if public_url="$(grep -Eo 'https://[^ ]+\.trycloudflare\.com' "$tmp_log" | head -n 1)" && [ -n "$public_url" ]; then
    break
  fi
  sleep 1
done

if [ -n "$public_url" ]; then
  printf '%s\n\n' 'void_map dev tunnel active.'
  printf '%-8s %s\n' 'Local:' "http://localhost:$port"
  printf '%-8s %s\n\n' 'Public:' "$public_url"
  printf '%s\n' 'WARNING: The public URL exposes your local filesystem browser and kismetdb data.'
  printf '%s\n' 'Shut down dev.sh when you are done testing.'
  printf '%s\n' 'The URL changes every time dev.sh restarts.'
else
  printf '%s\n' 'Waiting for cloudflared tunnel output. Press Ctrl+C to stop.'
fi

wait "$cloudflared_pid"
