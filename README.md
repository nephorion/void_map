# void_map

void_map is a lightweight local web application for exploring Kismet `.kismetdb` wardriving captures. It opens one read-only Kismet SQLite database at a time, displays GPS-backed RF observations on an interactive map, supports time filtering and replay, and estimates device positions with weighted-centroid triangulation.

## Requirements

- Ubuntu 22.04+ or another Debian-based distro, including DragonOS
- Python 3.8+
- A Kismet `.kismetdb` file, ideally with GPS data
- Internet access for first install and CDN-hosted frontend libraries/map tiles

Windows is not supported.

## Install

One-liner:

```bash
curl -sSL https://raw.githubusercontent.com/nephorion/void_map/main/install.sh | bash
```

The one-liner installs system dependencies, clones the repo into `~/void_map` if needed, syncs Python dependencies with `uv`, and prints the commands to start the app.

Clone and run:

```bash
git clone https://github.com/nephorion/void_map.git
cd void_map
chmod +x install.sh && ./install.sh
```

The installer uses `apt` for system packages, installs `uv`, runs `uv sync` to create the project environment from `pyproject.toml`, and attempts to install `cloudflared` on amd64 Linux for dev mode.

## Run

```bash
cd ~/void_map
./run.sh
```

Open `http://localhost:5000` if your browser does not open automatically.

## Use

1. Start the app with `./run.sh`.
2. Use the file picker to browse to a `.kismetdb` file.
3. Select the file and review the packet, device, and triangulated layers.
4. Use presets or the range sliders to filter time.
5. Use replay controls to play the selected range in cumulative or sliding-window mode.
6. Use the map layer dropdown to switch between CARTO and Google basemaps.

## Sample Data

A synthetic development database is included at `samples/sydney_cbd_dev.kismetdb`. It contains generated packet observations around Sydney CBD and can be selected from the file picker for local testing.

## Dev Mode

```bash
./dev.sh
```

Dev mode starts Flask locally and opens a temporary Cloudflare quick tunnel so you can test void_map from another device, such as a phone. The quick tunnel requires no Cloudflare account and the public URL changes on every restart.

Security warning: the tunnel URL is public. Anyone with the URL can access the filesystem browser and selected `.kismetdb` data exposed by the local app. Only use dev mode for short testing sessions and stop `dev.sh` when done.

## Check GPS Data

Verify whether a Kismet database has GPS-backed packet rows:

```bash
sqlite3 your.kismetdb "SELECT COUNT(*) FROM packets WHERE lat != 0 AND lon != 0;"
```

If this returns `0`, void_map can load the file but the map will not show packet locations.

## Check Sessions

Kismet schemas vary by version. Start with the tables list:

```bash
sqlite3 your.kismetdb ".tables"
```

If a `datasources` or `KISMET` metadata table is present, inspect it with:

```bash
sqlite3 your.kismetdb "SELECT * FROM datasources LIMIT 10;"
```

Kismet normally creates a new `.kismetdb` per session. void_map v1 handles one file at a time.

## API Summary

- `GET /api/browse` lists readable directories and `.kismetdb` files.
- `POST /api/select` sets the active database after validation.
- `POST /api/deselect` clears the active database.
- `GET /api/status` returns active file metadata.
- `GET /api/timerange` returns capture start/end timestamps.
- `GET /api/packets` returns GPS packet observations.
- `GET /api/devices` returns averaged device positions.
- `GET /api/triangulated` returns weighted-centroid device estimates.

All database connections are opened read-only with SQLite `query_only` enabled.

## Backend Dependencies

Backend dependencies are managed with `uv` through `pyproject.toml` and `uv.lock`.

```bash
uv sync
uv run python backend/app.py
```

## Known Limitations

- No authentication. Use locally only and do not expose the app to the internet.
- `/api/browse` exposes the local filesystem to the browser by design.
- Cloudflare dev tunnel URLs are public and unauthenticated.
- `cloudflared` auto-install only supports amd64; ARM devices require manual installation.
- Large `.kismetdb` files can be slow because v1 does not implement server-side pagination.
- CDN-hosted Kepler.gl/React/MapLibre assets and map tiles require internet access.
- Kismet SQLite schemas can vary; void_map detects common column names but may need adaptation for unusual databases.
- Weighted centroid triangulation is a heuristic and can be inaccurate indoors or in dense urban RF environments.
- Replay triangulation uses observations seen so far, not the full dataset.
- Multi-file and multi-session support are out of scope for v1.

## Contribute

Open an issue or pull request with a short description, test notes, and a sample schema when fixing Kismet compatibility issues. Do not include real capture data, private locations, or device identifiers in public reports.
