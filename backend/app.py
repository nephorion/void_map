import json
import math
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)

active_db_path = None


NO_FILE_RESPONSE = (
    {
        "error": "no_file_selected",
        "message": "No kismetdb file selected. Use the file picker to select one.",
    },
    503,
)


def error_response(error, message, status=400):
    return jsonify({"error": error, "message": message}), status


def reject_traversal(path):
    return ".." in Path(path).parts


def iso_from_ts(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts)).isoformat(timespec="seconds")


def connect_readonly(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def require_active_db():
    if not active_db_path:
        return None, NO_FILE_RESPONSE
    return active_db_path, None


def get_columns(conn, table):
    try:
        rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    except sqlite3.Error:
        return []
    return [row["name"] for row in rows]


def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def pick_column(columns, candidates):
    lower_map = {col.lower(): col for col in columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


def packet_column_map(conn):
    columns = get_columns(conn, "packets")
    if not columns:
        raise sqlite3.Error("packets table not found")
    return {
        "mac": pick_column(columns, ["mac", "devmac", "device", "source", "sourcemac"]),
        "lat": pick_column(columns, ["lat", "latitude", "gps_lat", "kismet.common.location.lat"]),
        "lon": pick_column(columns, ["lon", "lng", "longitude", "gps_lon", "kismet.common.location.lon"]),
        "signal": pick_column(columns, ["signal", "rssi", "dbm", "signal_dbm"]),
        "ts": pick_column(columns, ["ts_sec", "timestamp", "time", "ts", "packet_ts"]),
        "frequency": pick_column(columns, ["frequency", "freq", "channel_freq"]),
    }


def quote_ident(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def packet_select_sql(conn, filters=None):
    filters = filters or []
    cols = packet_column_map(conn)
    required = ["lat", "lon", "signal", "ts"]
    missing = [key for key in required if not cols[key]]
    if missing:
        raise sqlite3.Error("packets table missing required columns: " + ", ".join(missing))

    mac = quote_ident(cols["mac"]) if cols["mac"] else "''"
    freq = quote_ident(cols["frequency"]) if cols["frequency"] else "NULL"
    lat = quote_ident(cols["lat"])
    lon = quote_ident(cols["lon"])
    signal = quote_ident(cols["signal"])
    ts = quote_ident(cols["ts"])

    where = [
        f"{lat} IS NOT NULL",
        f"{lon} IS NOT NULL",
        f"NOT ({lat} = 0 AND {lon} = 0)",
        f"{signal} IS NOT NULL",
        f"{signal} != 0",
    ]
    params = []
    for clause, value in filters:
        where.append(clause.format(ts=ts))
        params.append(value)

    sql = f"""
        SELECT
          {mac} AS mac,
          CAST({lat} AS REAL) AS lat,
          CAST({lon} AS REAL) AS lon,
          CAST({signal} AS REAL) AS signal,
          CAST({ts} AS REAL) AS ts_sec,
          {freq} AS frequency
        FROM packets
        WHERE {' AND '.join(where)}
        ORDER BY CAST({ts} AS REAL)
    """
    return sql, params


def time_filters(conn):
    preset = request.args.get("preset")
    from_ts = request.args.get("from", type=float)
    to_ts = request.args.get("to", type=float)
    filters = []

    if preset and preset != "all":
        windows = {"last10m": 600, "last30m": 1800, "last1h": 3600, "last6h": 21600}
        if preset not in windows:
            return filters
        range_data = timerange_data(conn)
        if range_data["end_ts"] is not None:
            filters.append(("CAST({ts} AS REAL) >= ?", range_data["end_ts"] - windows[preset]))
        return filters

    if from_ts is not None:
        filters.append(("CAST({ts} AS REAL) >= ?", from_ts))
    if to_ts is not None:
        filters.append(("CAST({ts} AS REAL) <= ?", to_ts))
    return filters


def rows_to_packets(rows):
    packets = []
    for row in rows:
        ts_sec = int(row["ts_sec"]) if row["ts_sec"] is not None else None
        packets.append(
            {
                "mac": row["mac"] or "",
                "lat": row["lat"],
                "lon": row["lon"],
                "signal": row["signal"],
                "timestamp": iso_from_ts(ts_sec),
                "ts_sec": ts_sec,
                "frequency": row["frequency"],
            }
        )
    return packets


def packet_rows(conn, filters=None):
    sql, params = packet_select_sql(conn, filters)
    return conn.execute(sql, params).fetchall()


def device_metadata(conn):
    if not table_exists(conn, "devices"):
        return {}
    columns = get_columns(conn, "devices")
    mac_col = pick_column(columns, ["mac", "devmac", "device", "key"])
    type_col = pick_column(columns, ["type", "phyname", "devtype", "kismet.device.base.type"])
    json_col = pick_column(columns, ["device", "json", "data", "kismet_device_base_json"])
    if not mac_col:
        return {}

    select_parts = [f"{quote_ident(mac_col)} AS mac"]
    select_parts.append(f"{quote_ident(type_col)} AS raw_type" if type_col else "NULL AS raw_type")
    select_parts.append(f"{quote_ident(json_col)} AS raw_json" if json_col else "NULL AS raw_json")
    try:
        rows = conn.execute(f"SELECT {', '.join(select_parts)} FROM devices").fetchall()
    except sqlite3.Error:
        return {}

    return {row["mac"]: parse_device(row["raw_type"], row["raw_json"]) for row in rows if row["mac"]}


def parse_device(raw_type, raw_json):
    ssid = ""
    dtype = display_type(raw_type or "")
    if raw_json:
        try:
            data = json.loads(raw_json)
            flattened = flatten_json(data)
            ssid = first_value(
                flattened,
                [
                    "dot11.device.last_beaconed_ssid",
                    "kismet.device.base.name",
                    "ssid",
                    "name",
                ],
            ) or ""
            raw_type = raw_type or first_value(
                flattened, ["kismet.device.base.phyname", "phyname", "type"]
            )
            dtype = display_type(raw_type or "")
        except (TypeError, ValueError):
            pass
    if ssid in ("<hidden>", "<SSID Cloaked>", None):
        ssid = ""
    return {"type": dtype, "ssid": ssid}


def flatten_json(value, prefix=""):
    items = {}
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else key
            items.update(flatten_json(child, name))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.update(flatten_json(child, f"{prefix}.{index}"))
    else:
        items[prefix] = value
    return items


def first_value(flattened, keys):
    lower = {key.lower(): value for key, value in flattened.items()}
    for key in keys:
        if key.lower() in lower:
            return lower[key.lower()]
    for key, value in flattened.items():
        if key.lower().endswith("ssid") and value:
            return value
    return None


def display_type(raw_type):
    text = str(raw_type).lower()
    if "bluetooth" in text:
        return "Bluetooth"
    if "client" in text:
        return "Wi-Fi Client"
    if "ieee802.11" in text or "wifi" in text or "wi-fi" in text:
        return "Wi-Fi AP"
    return "Unknown"


def metadata(conn):
    rows = packet_rows(conn)
    packets = rows_to_packets(rows)
    macs = {packet["mac"] for packet in packets if packet["mac"]}
    ts_values = [packet["ts_sec"] for packet in packets if packet["ts_sec"] is not None]
    return {
        "device_count": len(macs),
        "packet_count": len(packets),
        "has_gps": len(packets) > 0,
        "start_time": iso_from_ts(min(ts_values)) if ts_values else None,
        "end_time": iso_from_ts(max(ts_values)) if ts_values else None,
    }


def timerange_data(conn):
    rows = packet_rows(conn)
    ts_values = [float(row["ts_sec"]) for row in rows if row["ts_sec"] is not None]
    if not ts_values:
        return {
            "start_ts": None,
            "end_ts": None,
            "start_human": None,
            "end_human": None,
            "duration_seconds": 0,
        }
    start = int(min(ts_values))
    end = int(max(ts_values))
    return {
        "start_ts": start,
        "end_ts": end,
        "start_human": iso_from_ts(start),
        "end_human": iso_from_ts(end),
        "duration_seconds": max(0, end - start),
    }


def haversine_m(lat1, lon1, lat2, lon2):
    earth_radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def triangulate(packets, metadata_by_mac=None):
    metadata_by_mac = metadata_by_mac or {}
    grouped = {}
    for packet in packets:
        grouped.setdefault(packet["mac"], []).append(packet)
    results = []
    for mac, observations in grouped.items():
        if not mac:
            continue
        min_signal = min(obs["signal"] for obs in observations)
        weights = [obs["signal"] - min_signal + 1 for obs in observations]
        weight_sum = sum(weights) or len(observations)
        est_lat = sum(obs["lat"] * weight for obs, weight in zip(observations, weights)) / weight_sum
        est_lon = sum(obs["lon"] * weight for obs, weight in zip(observations, weights)) / weight_sum
        min_lat = min(obs["lat"] for obs in observations)
        max_lat = max(obs["lat"] for obs in observations)
        min_lon = min(obs["lon"] for obs in observations)
        max_lon = max(obs["lon"] for obs in observations)
        spread = haversine_m(min_lat, min_lon, max_lat, max_lon)
        count = len(observations)
        if count < 3 or (count <= 10 and spread < 50):
            confidence = "low"
        elif count <= 10:
            confidence = "medium"
        else:
            confidence = "high" if spread >= 50 else "medium"
        info = metadata_by_mac.get(mac, {"ssid": "", "type": "Unknown"})
        signals = [obs["signal"] for obs in observations]
        results.append(
            {
                "mac": mac,
                "ssid": info.get("ssid", ""),
                "type": info.get("type", "Unknown"),
                "est_lat": est_lat,
                "est_lon": est_lon,
                "confidence": confidence,
                "observation_count": count,
                "signal_range_dbm": [min(signals), max(signals)],
                "avg_signal": sum(signals) / count,
            }
        )
    return results


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(FRONTEND_DIR, "favicon.svg", mimetype="image/svg+xml")


@app.get("/api/health")
def health():
    return jsonify({"app": "void_map", "status": "ok"})


@app.get("/api/browse")
def browse():
    path = request.args.get("path") or str(Path.home())
    if reject_traversal(path):
        return error_response("invalid_path", "Path traversal not permitted")
    directory = Path(path).expanduser()
    if not directory.exists() or not directory.is_dir() or not os.access(directory, os.R_OK):
        return error_response("invalid_path", "Path does not exist or is not readable")
    entries = []
    for child in directory.iterdir():
        if child.name.startswith("."):
            continue
        is_dir = child.is_dir()
        is_kismetdb = child.is_file() and child.name.endswith(".kismetdb")
        if not is_dir and not is_kismetdb:
            continue
        stat = child.stat()
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "type": "directory" if is_dir else "file",
                "size_mb": None if is_dir else round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "is_kismetdb": is_kismetdb,
            }
        )
    entries.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
    parent = str(directory.parent) if directory.parent != directory else None
    return jsonify({"current_path": str(directory), "parent_path": parent, "entries": entries})


@app.post("/api/select")
def select_file():
    global active_db_path
    payload = request.get_json(silent=True) or {}
    path = payload.get("path", "")
    if reject_traversal(path):
        return error_response("invalid_path", "Path traversal not permitted")
    db_path = Path(path).expanduser()
    if not db_path.exists() or not db_path.is_file() or not os.access(db_path, os.R_OK):
        return error_response("invalid_path", "Path does not exist or is not readable")
    if not str(db_path).endswith(".kismetdb"):
        return error_response("invalid_path", "Path must end in .kismetdb")
    try:
        with connect_readonly(str(db_path)) as conn:
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            meta = metadata(conn)
    except sqlite3.Error as exc:
        return error_response("invalid_database", f"Could not read SQLite database: {exc}")
    active_db_path = str(db_path)
    return jsonify({"path": active_db_path, **meta})


@app.post("/api/deselect")
def deselect_file():
    global active_db_path
    active_db_path = None
    return jsonify({"status": "ok"})


@app.get("/api/status")
def status():
    db_path, error = require_active_db()
    if error:
        return error
    with connect_readonly(db_path) as conn:
        meta = metadata(conn)
    return jsonify({"db_path": db_path, "filename": Path(db_path).name, **meta})


@app.get("/api/timerange")
def timerange():
    db_path, error = require_active_db()
    if error:
        return error
    with connect_readonly(db_path) as conn:
        return jsonify(timerange_data(conn))


@app.get("/api/packets")
def packets():
    db_path, error = require_active_db()
    if error:
        return error
    with connect_readonly(db_path) as conn:
        rows = packet_rows(conn, time_filters(conn))
    return jsonify(rows_to_packets(rows))


@app.get("/api/devices")
def devices():
    db_path, error = require_active_db()
    if error:
        return error
    with connect_readonly(db_path) as conn:
        packets = rows_to_packets(packet_rows(conn, time_filters(conn)))
        meta = device_metadata(conn)
    grouped = {}
    for packet in packets:
        grouped.setdefault(packet["mac"], []).append(packet)
    results = []
    for mac, observations in grouped.items():
        if not mac:
            continue
        info = meta.get(mac, {"ssid": "", "type": "Unknown"})
        signals = [obs["signal"] for obs in observations]
        results.append(
            {
                "mac": mac,
                "type": info.get("type", "Unknown"),
                "ssid": info.get("ssid", ""),
                "avg_lat": sum(obs["lat"] for obs in observations) / len(observations),
                "avg_lon": sum(obs["lon"] for obs in observations) / len(observations),
                "avg_signal": sum(signals) / len(signals),
                "first_seen": iso_from_ts(min(obs["ts_sec"] for obs in observations)),
                "last_seen": iso_from_ts(max(obs["ts_sec"] for obs in observations)),
                "observation_count": len(observations),
            }
        )
    return jsonify(results)


@app.get("/api/triangulated")
def triangulated():
    db_path, error = require_active_db()
    if error:
        return error
    with connect_readonly(db_path) as conn:
        packets = rows_to_packets(packet_rows(conn, time_filters(conn)))
        meta = device_metadata(conn)
    return jsonify(triangulate(packets, meta))


if __name__ == "__main__":
    host = os.environ.get("VOID_MAP_HOST", "127.0.0.1")
    port = int(os.environ.get("VOID_MAP_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
