"""Pickup-window persistence: default rules, per-wish snapshots, row shaping."""
import json

from app.engines import pickup_window as pw
from app.modules.pickup_window import projection

DEFAULT_WINDOW = {"weekdays": [5, 6], "start_hour": 9, "end_hour": 18}
DEFAULT_TIMEZONE = "Asia/Shanghai"

SET_WINDOW_KEY = "pickup_window"
SET_TZ_KEY = "pickup_timezone"


def dumps(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False)


def loads(text: str | None) -> dict | None:
    """Parse a snapshot JSON column; None or corrupt content yields None."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def default_snapshot() -> dict:
    return {"version": pw.SNAPSHOT_VERSION, **DEFAULT_WINDOW, "timezone": DEFAULT_TIMEZONE}


def load_rules(c) -> dict:
    """Read default window/timezone from settings, falling back on missing/corrupt rows."""
    rows = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
    window = dict(DEFAULT_WINDOW)
    raw = loads(rows.get(SET_WINDOW_KEY))
    if raw is not None:
        try:
            window = pw.validate_window(raw)
        except pw.WindowError:
            window = dict(DEFAULT_WINDOW)
    tz = rows.get(SET_TZ_KEY) or DEFAULT_TIMEZONE
    try:
        pw.validate_window({"weekdays": [0], "start_hour": 0, "end_hour": 24, "timezone": tz})
    except pw.WindowError:
        tz = DEFAULT_TIMEZONE
    return {"window": window, "timezone": tz}


def save_rules(c, window: dict, timezone: str) -> dict:
    """Validate then UPSERT both settings keys. Only future wishes are affected."""
    normalized = pw.validate_window(
        {**window, "timezone": timezone}, require_timezone=True
    )
    tz = normalized.pop("timezone")
    c.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (SET_WINDOW_KEY, dumps(normalized)),
    )
    c.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (SET_TZ_KEY, tz),
    )
    return {"window": normalized, "timezone": tz}


def build_snapshot(override: dict | None, default_window: dict, default_tz: str) -> dict:
    """Merge a wish-level override over the defaults and freeze a full snapshot."""
    merged = {**default_window, "timezone": default_tz}
    if override:
        for key in ("weekdays", "start_hour", "end_hour", "timezone"):
            value = override.get(key)
            if value is not None:
                merged[key] = value
    normalized = pw.validate_window(merged, require_timezone=True)
    return {"version": pw.SNAPSHOT_VERSION, **normalized}


def attach_state(row: dict, now_utc) -> dict:
    """Parse a wish row's JSON snapshot into an object and attach pickup_state."""
    snap = loads(row.get("pickup_window"))
    row["pickup_window"] = snap
    row["pickup_state"] = projection.project(snap, now_utc) if snap is not None else None
    return row
