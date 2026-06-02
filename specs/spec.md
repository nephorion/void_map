# void_map — App Specification

> Cyberpunk RF signal visualiser and wardriving replay tool for Kismet `.kismetdb` data.

---

## Overview

void_map is a lightweight local web application that reads a Kismet `.kismetdb` file and
visualises device detections on an interactive Kepler.gl map. It supports a UI-driven file
picker, time-range filtering, sliding window and cumulative replay animation, and weighted
centroid triangulation of device positions from RSSI observations.

Designed to be installed with a single shell script from a public git repository and run
with no configuration. No cloud dependency. No authentication. Local use only.

---

## Goals

- Zero cloud dependency — runs entirely locally
- Single command install from a public git repo
- Non-technical friendly — minimal configuration required
- Read-only — never modifies the kismetdb file
- UI-first file selection — no command line arguments needed to run
- Supports replay animation of captured wardriving sessions

---

## What void_map Does NOT Read

Kismet creates several log file types. void_map only reads `.kismetdb`. The following are
ignored:

| File | Description | Used? |
|---|---|---|
| `.kismetdb` | Main SQLite database | ✅ Yes |
| `.pcapng` | Raw packet capture | ❌ No |
| `.wiglecsv` | WiGLE wardriving format | ❌ No |
| `.kismet` | Legacy format | ❌ No |

> **Note:** Kismet creates a new `.kismetdb` file per session. void_map handles one file
> at a time. Multi-file/multi-session support is out of scope for v1.

---

## Repository Structure

```
void_map/
├── install.sh          # One-shot install script (system deps + uv + cloudflared)
├── run.sh              # Start the app
├── dev.sh              # Dev mode: starts app + Cloudflare tunnel
├── README.md
├── pyproject.toml      # uv-managed Python project dependencies
├── uv.lock             # Locked uv dependency graph
├── backend/
│   └── app.py          # Flask API
└── frontend/
    └── index.html      # Single-file frontend: file picker + Kepler.gl map
```

---

## Install

### One-liner
```bash
curl -sSL https://raw.githubusercontent.com/nephorion/void_map/main/install.sh | bash
```

### Clone and run
```bash
git clone https://github.com/nephorion/void_map.git
cd void_map
chmod +x install.sh && ./install.sh
```

### Target Platform

Ubuntu 22.04+ or any Debian-based distro including DragonOS. Uses `apt` as the system
package manager. Windows is not supported.

---

### install.sh — Full Behaviour

The script must be idempotent — safe to run multiple times without side effects.

**Step 1 — Check sudo access**

Exit immediately with a clear message if `sudo` is not available:
```
ERROR: This script requires sudo access to install system packages.
```

**Step 2 — System dependencies via apt**

Run `sudo apt-get update -qq` then install the following if not already present:

| Package | Why |
|---|---|
| `python3` | Runtime |
| `python3-dev` | Required to compile some Python packages |
| `curl` | Used to install uv and cloudflared |
| `sqlite3` | Allows user to inspect kismetdb files from the command line |
| `git` | In case the user ran the curl one-liner and needs git available |

> `python3-pip` and `python3-venv` are not required — `uv` handles both.

If `install.sh` is run from the curl one-liner and the current directory is not already a
void_map checkout, clone `https://github.com/nephorion/void_map.git` into `~/void_map`
or `$VOID_MAP_INSTALL_DIR` when set. If the target checkout already exists, pull with
`git pull --ff-only` and continue. If the target path exists but is not a git checkout,
exit with a clear error.

**Step 3 — Verify Python version**

Confirm the detected Python is 3.8 or higher. If not, exit with:
```
ERROR: Python 3.8+ is required. Found: <version>.
On Ubuntu 20.04 you may need to install python3.10 manually.
```

**Step 4 — uv (Python package manager)**

Install `uv` using the official installer:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Source the shell env immediately so `uv` is available in the current script session:
```bash
source "$HOME/.cargo/env" 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"
```

Verify by running `uv --version`. If this fails, exit with:
```
ERROR: uv installation failed. Try installing manually:
  curl -LsSf https://astral.sh/uv/install.sh | sh
Then re-run install.sh.
```

`uv` is the only Python package and environment manager for this project. Do not use
`pip`, `uv pip`, `python3 -m venv`, or a `requirements.txt` file anywhere in the project.

**Step 5 — Cloudflared**

Install the Cloudflare tunnel client for dev mode. Use the official deb package for
Linux amd64:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
  -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
```

Check architecture first with `uname -m`. If not amd64, print a warning and skip — do
not exit. The app works without cloudflared; only dev.sh is affected:
```
WARNING: cloudflared auto-install only supports amd64.
dev.sh will not work. Download cloudflared manually from:
  https://github.com/cloudflare/cloudflared/releases
```

Verify by running `cloudflared --version`. If it fails after install, print the same
warning and continue.

**Step 6 — Python environment and packages**

Use `uv` to create/sync the project environment and install dependencies from
`pyproject.toml`:
```bash
uv sync
```

`uv sync` creates `.venv` if needed and installs the locked dependencies. Do not use
`pip`, `uv pip`, `python3 -m venv`, or a `requirements.txt` file anywhere in the project.

**pyproject.toml dependencies:**
```
flask>=2.3
flask-cors>=4.0
```

**Step 7 — Permissions**

```bash
chmod +x run.sh dev.sh
```

**Step 8 — Success output**

```
✅ void_map installed successfully.

To start:
  ./run.sh

To start in dev mode (Cloudflare tunnel for testing on other devices):
  ./dev.sh

To verify a kismetdb has GPS data:
  sqlite3 your.kismetdb "SELECT COUNT(*) FROM packets WHERE lat != 0 AND lon != 0;"
```

---

## Running

### Normal Use

```bash
./run.sh
```

**run.sh must:**
- Take no arguments
- Activate the uv environment and start Flask:
  ```bash
  uv run python backend/app.py
  ```
- Print `void_map running at http://localhost:5000`
- Attempt `xdg-open http://localhost:5000` to open the browser automatically
- Print the URL clearly if xdg-open is not available or fails

---

### Dev Mode — Cloudflare Tunnel

```bash
./dev.sh
```

**dev.sh must:**
- Take no arguments
- Check `cloudflared` is installed; exit with install instructions if not
- Start Flask in the background on `localhost:5000`
- If `localhost:5000` is already in use, select the next free port in `5001-5020`
  and tunnel to that port instead
- Verify `/api/health` returns `app: void_map` before starting the tunnel, so dev mode
  never tunnels to an unrelated process
- Start a Cloudflare quick tunnel:
  ```bash
  cloudflared tunnel --url http://localhost:<selected-port>
  ```
- Parse the `*.trycloudflare.com` URL from cloudflared's stderr output and print it:
  ```
  ✅ void_map dev tunnel active.

  Local:   http://localhost:<selected-port>
  Public:  https://random-words.trycloudflare.com

  ⚠️  The public URL exposes your local filesystem browser and kismetdb data.
      Shut down dev.sh when you are done testing.
      The URL changes every time dev.sh restarts.
  ```
- On Ctrl+C, kill both Flask and cloudflared cleanly

**How the Cloudflare quick tunnel works:**

`cloudflared tunnel --url` creates a temporary unauthenticated public HTTPS tunnel
requiring no Cloudflare account. The URL is randomly generated and valid only for the
lifetime of the process. Use it to open void_map on a phone or a different machine on
a different network during development.

**Parsing the tunnel URL:**

cloudflared prints to stderr in this format:
```
INF | https://random-words.trycloudflare.com |
```
Watch stderr for any line containing `trycloudflare.com` and extract the URL. Print it
as soon as it appears — do not wait for the tunnel to be fully ready.

---

## Backend

### Tech Stack
- Python 3.8+
- Flask
- flask-cors
- `sqlite3` (Python stdlib)

### SQLite Access Rules

Always open databases read-only:
```python
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
conn.execute("PRAGMA query_only = ON")
```

Never write to or modify any kismetdb file under any circumstances.

### Active File State

The backend holds the currently selected db path in a module-level variable. It starts
as `None` on launch.

All data endpoints (`/api/packets`, `/api/devices`, `/api/triangulated`, `/api/status`,
`/api/timerange`) return HTTP `503` if no file has been selected:
```json
{
  "error": "no_file_selected",
  "message": "No kismetdb file selected. Use the file picker to select one."
}
```

### Global Packet Filtering Rules

Applied to all endpoints that query the packets table:
- Exclude rows where `lat = 0` AND `lon = 0`
- Exclude rows where `lat IS NULL` OR `lon IS NULL`
- Exclude rows where `signal = 0` OR `signal IS NULL`

---

## API Endpoints

### GET /api/browse

Returns the contents of a local filesystem directory for the file picker UI.

**Query parameters:**

| Parameter | Default | Description |
|---|---|---|
| `path` | User home directory | Directory to list |

**Response:**
```json
{
  "current_path": "/home/user/kismet_logs",
  "parent_path": "/home/user",
  "entries": [
    {
      "name": "kismet-20240101-wardriving.kismetdb",
      "path": "/home/user/kismet_logs/kismet-20240101-wardriving.kismetdb",
      "type": "file",
      "size_mb": 14.2,
      "modified": "2024-01-01T11:00:00",
      "is_kismetdb": true
    },
    {
      "name": "old_logs",
      "path": "/home/user/kismet_logs/old_logs",
      "type": "directory",
      "size_mb": null,
      "modified": "2024-01-01T09:00:00",
      "is_kismetdb": false
    }
  ]
}
```

**Rules:**
- Only return entries where `type = "directory"` OR filename ends in `.kismetdb`
- Hide hidden files and directories (names starting with `.`)
- Sort: directories first, then files, both alphabetically
- Reject any path containing `..` — return `400`:
  ```json
  { "error": "invalid_path", "message": "Path traversal not permitted" }
  ```
- If the path does not exist or is not readable, return `400`:
  ```json
  { "error": "invalid_path", "message": "Path does not exist or is not readable" }
  ```

---

### POST /api/select

Sets the active kismetdb file. Called when the user clicks a file in the picker.

**Request body:**
```json
{ "path": "/home/user/kismet_logs/kismet-20240101-wardriving.kismetdb" }
```

**Validation (reject with `400` if any fail):**
- Path must not contain `..`
- Path must exist and be readable
- Path must end in `.kismetdb`
- Must open successfully as a SQLite database (attempt a test query)

**On success**, run a GPS check and return:
```json
{
  "path": "/home/user/kismet_logs/kismet-20240101-wardriving.kismetdb",
  "device_count": 128,
  "packet_count": 4821,
  "has_gps": true,
  "start_time": "2024-01-01T10:00:00",
  "end_time": "2024-01-01T11:00:00"
}
```

If `has_gps` is false (all lat/lon are 0 or null), still return `200` with
`has_gps: false`. The frontend shows a warning but allows the user to load the file.

---

### POST /api/deselect

Clears the active file and returns the UI to the file picker.

**Request body:** none

**Response:**
```json
{ "status": "ok" }
```

---

### GET /api/status

Returns metadata for the currently selected db. Returns `503` if no file is selected.

**Response:**
```json
{
  "db_path": "/path/to/file.kismetdb",
  "filename": "kismet-20240101-wardriving.kismetdb",
  "device_count": 128,
  "packet_count": 4821,
  "start_time": "2024-01-01T10:00:00",
  "end_time": "2024-01-01T11:00:00"
}
```

---

### GET /api/timerange

Returns the earliest and latest timestamps in the active db.

**Response:**
```json
{
  "start_ts": 1704067200,
  "end_ts": 1704070800,
  "start_human": "2024-01-01T10:00:00",
  "end_human": "2024-01-01T11:00:00",
  "duration_seconds": 3600
}
```

---

### GET /api/packets

Returns individual packet observations with per-packet GPS. Used for heatmap and replay.

**Query parameters (all optional):**

| Parameter | Type | Description |
|---|---|---|
| `from` | Unix timestamp | Include packets at or after this time |
| `to` | Unix timestamp | Include packets at or before this time |
| `preset` | string | Convenience shorthand (see below) |

**Preset values** (relative to the latest timestamp in the db, not wall clock):

| Preset | Window |
|---|---|
| `last10m` | Last 10 minutes |
| `last30m` | Last 30 minutes |
| `last1h` | Last 1 hour |
| `last6h` | Last 6 hours |

If `preset` and explicit `from`/`to` are both provided, `preset` takes precedence.
If no parameters are provided, all data is returned.

**Response:**
```json
[
  {
    "mac": "AA:BB:CC:DD:EE:FF",
    "lat": -33.123,
    "lon": 151.456,
    "signal": -72,
    "timestamp": "2024-01-01T10:00:01",
    "ts_sec": 1704067201,
    "frequency": 2437
  }
]
```

> `ts_sec` must be included — the frontend uses it to drive replay ordering.

---

### GET /api/devices

Returns one row per unique device with averaged GPS and metadata.

**Query parameters:** same as `/api/packets`

**Response:**
```json
[
  {
    "mac": "AA:BB:CC:DD:EE:FF",
    "type": "Wi-Fi AP",
    "ssid": "MyNetwork",
    "avg_lat": -33.123,
    "avg_lon": 151.456,
    "avg_signal": -67,
    "first_seen": "2024-01-01T10:00:00",
    "last_seen": "2024-01-01T10:05:00",
    "observation_count": 42
  }
]
```

**Device type mapping:**

| Kismet type | Display value |
|---|---|
| `IEEE802.11` AP | `Wi-Fi AP` |
| `IEEE802.11` client | `Wi-Fi Client` |
| `bluetooth` | `Bluetooth` |
| anything else | `Unknown` |

**SSID:** Extract from the JSON blob in the devices table. Default to `""` if null,
hidden, or missing.

---

### GET /api/triangulated

Returns one estimated position per unique device calculated using weighted centroid.

**Query parameters:** same as `/api/packets`

**Response:**
```json
[
  {
    "mac": "AA:BB:CC:DD:EE:FF",
    "ssid": "MyNetwork",
    "type": "Wi-Fi AP",
    "est_lat": -33.124,
    "est_lon": 151.457,
    "confidence": "high",
    "observation_count": 42,
    "signal_range_dbm": [-45, -87],
    "avg_signal": -62
  }
]
```

**Calculation:**

RSSI values are negative dBm integers (-45 is strong, -90 is weak). Normalise to
positive weights:

```python
weight = signal - min_signal_in_dataset + 1

est_lat = sum(lat * weight) / sum(weight)
est_lon = sum(lon * weight) / sum(weight)
```

**Confidence scoring:**

Spread is the bounding box diagonal of all observations for that device in metres,
calculated using Haversine. Implement Haversine using Python stdlib `math` only —
no external geo libraries.

| Condition | Confidence |
|---|---|
| Fewer than 3 observations | `low` |
| 3–10 observations AND spread < 50m | `low` |
| 3–10 observations AND spread ≥ 50m | `medium` |
| More than 10 observations AND spread ≥ 50m | `high` |

Devices with fewer than 3 observations are still returned, flagged as `low`.

---

## Frontend

### Tech
- Single self-contained `index.html` — no build step, no npm
- Kepler.gl loaded via CDN (unpkg) — pin to a specific version
- React and ReactDOM loaded via CDN
- `react-is` loaded via CDN before `styled-components` because styled-components'
  UMD bundle requires the global ReactIs object
- `redux` and `react-redux` loaded via CDN before Kepler.gl because Kepler.gl's UMD
  bundle requires the global Redux and ReactRedux objects
- `styled-components` loaded via CDN before Kepler.gl because Kepler.gl's UMD bundle
  requires the global styled-components object
- All CORS headers returned by all backend endpoints

### Two Screens

The frontend has two distinct screens. Only one is visible at a time. Switching between
them is handled in JavaScript — no page reload.

---

## Screen 1 — File Picker

Shown on first load and whenever no file is active.

### Layout

- **Header:** `void_map` name and a one-line description
- **Breadcrumb trail:** current directory path as clickable segments
  - e.g. `/ home / user / kismet_logs`
  - Each segment navigates to that directory on click
- **`↑ Parent directory` button:** at the top of the listing; disabled at filesystem root
- **Directory/file listing:** below the breadcrumb

### Listing Entries

**Directories:** folder icon, name, last modified. Click to navigate into.

**`.kismetdb` files:** database icon, filename, size in MB, last modified. Click to select.

### On File Click

1. Call `POST /api/select` with the file path
2. Show inline loading state on that file row
3. If `has_gps: false` in response, show a yellow warning banner:
   ```
   ⚠️ This file has no GPS data. The map will load but no points will be visible.
   ```
   With two buttons: `Load anyway` and `Choose a different file`
4. If `has_gps: true`, switch to Screen 2 immediately

### Error Handling

- `POST /api/select` error → show the error message inline below the filename, do not navigate
- `/api/browse` failure → show `"Cannot read this directory"` with a back button

### Initial Directory

On first load, call `GET /api/browse` with no path (defaults to home directory).
If no `.kismetdb` files are found in the home directory, show:
```
No .kismetdb files found here.
Navigate to the folder where Kismet saves its logs.
```

---

## Screen 2 — Map View

### Load Sequence

1. Fetch `/api/status` → populate header bar
2. Fetch `/api/timerange` → initialise time range controls
3. Fetch `/api/packets`, `/api/devices`, `/api/triangulated` with current time range params
4. Load all three into Kepler.gl as separate named layers
5. Auto-centre and zoom to fit the data bounding box

Auto-centre on initial file load only. Never move the map automatically after that.

---

## Kepler.gl Layers

### Layer 1 — Raw Packets (heatmap)
- Source: `/api/packets`
- Render as: heatmap
- Colour by: signal strength (RSSI)
- Default: visible

### Layer 2 — Averaged Device Positions
- Source: `/api/devices`
- Render as: point layer
- Colour by: device type
- Default: visible

### Layer 3 — Triangulated Positions
- Source: `/api/triangulated`
- Render as: distinct point marker (visually different shape or size from Layer 2)
- Colour by confidence: green = `high`, amber = `medium`, red = `low`
- When raw packets and triangulated positions are visible, draw faint lines from each raw
  packet observation to its device's triangulated estimate
- On click: popup showing MAC, SSID, confidence, observation count, signal range, and
  highlight the raw packet observations and connection lines that contributed to that
  triangulated estimate
- Default: visible

---

## UI Controls — Screen 2

### Header Bar

Left to right:
- App name: **void_map**
- Selected filename (not full path)
- Device count
- Packet count
- `✕ Change file` button (far right) — calls `POST /api/deselect` and returns to Screen 1,
  clearing all map data

### Layer Toggles

Three toggle buttons in the header bar to show/hide layers independently:
- `Raw Packets`
- `Device Positions`
- `Triangulated`

### Basemap Selector

A dropdown in the header bar lets the user switch the map tile layer without reloading
the selected `.kismetdb` file or losing overlay data:
- `CARTO Dark`
- `CARTO Light`
- `Google Roadmap`
- `Google Satellite`

### Time Range Controls

Panel below the header bar:
- **Preset buttons:** `Last 10m` `Last 30m` `Last 1h` `Last 6h` `All`
- **Dual-handle range slider** spanning the full session timeline for custom from/to
- **Human readable range display**, e.g. `10:00:00 → 10:30:00`
- **Apply button** — re-fetches all three endpoints and reloads all layers

Disabled while replay is active.

### Replay Toolbar

Below the time range controls:

| Control | Description |
|---|---|
| `▶ / ⏸` | Play / Pause toggle |
| `⏹` | Reset — clears points, returns to start of time range |
| Speed | `0.5x` `1x` `2x` `5x` `10x` |
| Mode | `Cumulative` / `Sliding Window` toggle |
| Window | `1m` `5m` `10m` `30m` dropdown (Sliding Window mode only) |
| Scrubber | Progress bar through the selected time range |
| Timestamp | Current replay time, e.g. `10:14:32` |

### Replay Behaviour

All data for the selected range is fetched upfront and held in browser memory. Replay is
entirely client-side — no backend calls during playback.

On Play, the frontend steps through packets ordered by `ts_sec`. Each step represents
one real-second of replay time, adjusted by the speed multiplier.

**Cumulative mode:** Points accumulate on the map and never disappear. Good for seeing
overall session coverage.

**Sliding Window mode:** Only points within the rolling window ending at the current
replay moment are visible. Points older than the window size drop off. Default mode.
Default window size: 5 minutes.

During replay:
- Triangulated positions recalculate incrementally from observations seen so far
- Scrubber advances with playback
- Replay stops automatically at the end of the time range

### Large Dataset Warning

If packet count for the selected range exceeds 50,000, show before loading:
```
⚠️ Large dataset (N packets) — replay may be slow.
Consider selecting a shorter time range.
```

---

## Error States

| Condition | Message |
|---|---|
| No GPS data in file | `"No GPS data found in this kismetdb file"` |
| Backend unreachable | `"Cannot connect to backend — is run.sh running?"` |
| No data in selected time range | `"No data found in the selected time range"` |
| No file selected (503 from API) | Return to Screen 1 automatically |

Show a loading spinner while fetching. All error messages appear in the map area, not
as browser alerts.

---

## README.md Must Cover

- What void_map is (one paragraph)
- Requirements: Ubuntu 22.04+ / Debian-based, Python 3.8+, a `.kismetdb` file with GPS data
- Install: the curl one-liner and the clone method
- How to run (`./run.sh`)
- How to use dev mode (`./dev.sh`) and what the Cloudflare tunnel is for
- Security warning: the tunnel URL is public and exposes the filesystem browser and kismetdb data
- How to verify a kismetdb has GPS data:
  ```bash
  sqlite3 your.kismetdb "SELECT COUNT(*) FROM packets WHERE lat != 0 AND lon != 0;"
  ```
- How to check which sessions are in a kismetdb file
- Known limitations
- How to contribute

---

## Known Limitations

- No authentication — local use only. Do not expose to the internet.
- `/api/browse` exposes the local filesystem to the browser. This is intentional for
  local use but means the Cloudflare dev tunnel would allow anyone with the URL to browse
  your filesystem. Shut down `dev.sh` when not actively testing.
- The Cloudflare quick tunnel URL is public with no password — anyone with it can access
  your data. Use only for short-lived testing.
- The tunnel URL changes every time `dev.sh` restarts.
- `cloudflared` auto-install only supports amd64. ARM devices require manual installation.
- Large kismetdb files (100k+ packets) may be slow to load for replay — no server-side
  pagination in v1.
- Kepler.gl via CDN requires an internet connection to load map tiles and the library.
- Tested on Ubuntu 22.04 and DragonOS. Other Debian-based distros should work.
  Windows is not supported.
- Weighted centroid triangulation assumes open environment with no multipath — accuracy
  degrades significantly indoors or in dense urban areas.
- Confidence scoring is a simple heuristic, not a statistical confidence interval.
- Triangulation during replay uses only observations seen so far, not the full dataset.
- Replay timing depends on the browser tab being active and not throttled by the OS.
- Multi-file / multi-session support is not available in v1.
- Only one `.kismetdb` file can be active at a time.

---

## Out of Scope for v1

- Multi-file / multi-session support
- Live/streaming updates from a running Kismet instance
- True trilateration using path loss models
- Angle of arrival / directional antenna support
- MLAT (multilateration)
- Authentication
- BigQuery integration
- Docker container
- Sub-second replay granularity
- Controlling Kismet from the UI
- Filtering or searching devices in the UI
- Exporting data from the UI
