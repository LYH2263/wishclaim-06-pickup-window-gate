"""Pickup time-window gating.

A window snapshot is a plain dict::

    {"version": 1, "weekdays": [5, 6], "start_hour": 9, "end_hour": 18,
     "timezone": "Asia/Shanghai"}

Weekdays use Python's convention (Monday=0 ... Sunday=6). The daily segment
is half-open ``[start_hour, end_hour)`` in the snapshot's local wall clock;
cross-midnight segments are rejected by :func:`validate_window`.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

SNAPSHOT_VERSION = 1


class WindowError(ValueError):
    """Validation failure carrying human-readable error strings."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _as_int(value, field: str, errors: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{field} 必须是整数")
        return None
    return value


def validate_window(raw: dict, *, require_timezone: bool = False) -> dict:
    """Validate and normalize a window (or snapshot) dict.

    Returns ``{"weekdays": [...sorted unique ints...], "start_hour", "end_hour",
    "timezone"?}``. Raises :class:`WindowError` collecting every problem.
    """
    errors: list[str] = []
    if not isinstance(raw, dict):
        raise WindowError(["取货窗格式不正确"])

    weekdays_raw = raw.get("weekdays")
    weekdays: list[int] = []
    if not isinstance(weekdays_raw, list) or len(weekdays_raw) == 0:
        errors.append("星期集合不能为空")
    else:
        for d in weekdays_raw:
            n = _as_int(d, "星期", errors)
            if n is not None and not (0 <= n <= 6):
                errors.append("星期必须在 0（周一）到 6（周日）之间")
            elif n is not None:
                weekdays.append(n)
        weekdays = sorted(set(weekdays))

    start = _as_int(raw.get("start_hour"), "开始小时", errors)
    end = _as_int(raw.get("end_hour"), "结束小时", errors)
    if start is not None and not (0 <= start <= 24):
        errors.append("开始小时必须在 0 到 24 之间")
    if end is not None and not (0 <= end <= 24):
        errors.append("结束小时必须在 0 到 24 之间")
    if start is not None and end is not None and 0 <= start <= 24 and 0 <= end <= 24 and end <= start:
        errors.append("结束小时必须大于开始小时（不支持跨午夜）")

    tzname = raw.get("timezone")
    if tzname is not None and not isinstance(tzname, str):
        errors.append("时区必须是 IANA 时区名称字符串")
        tzname = None
    if require_timezone and not tzname:
        errors.append("时区必填")
    zone = None
    if tzname:
        try:
            zone = ZoneInfo(tzname)
        except Exception:
            errors.append(f"无法识别的时区：{tzname}")

    if errors:
        raise WindowError(errors)

    out = {"weekdays": weekdays, "start_hour": start, "end_hour": end}
    if zone is not None:
        out["timezone"] = tzname
    return out


def to_local(snapshot: dict, now_utc: datetime) -> datetime:
    """Convert ``now_utc`` to the snapshot timezone; naive input means UTC."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(ZoneInfo(snapshot["timezone"]))


def is_open(snapshot: dict, now_utc: datetime) -> bool:
    """True iff ``now_utc`` falls inside the pickup window."""
    local = to_local(snapshot, now_utc)
    if local.weekday() not in snapshot["weekdays"]:
        return False
    # 本地墙钟分钟数比较；end=24（1440）天然覆盖全天，避开非法的 time(24)
    minutes = local.hour * 60 + local.minute + local.second / 60
    return snapshot["start_hour"] * 60 <= minutes < snapshot["end_hour"] * 60


def _day_bounds(snapshot: dict, local_day, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(local_day, time(snapshot["start_hour"]), tzinfo=zone)
    if snapshot["end_hour"] == 24:
        end = datetime.combine(local_day + timedelta(days=1), time(0), tzinfo=zone)
    else:
        end = datetime.combine(local_day, time(snapshot["end_hour"]), tzinfo=zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def next_opening(snapshot: dict, now_utc: datetime, *, within_days: int = 14) -> dict | None:
    """First window interval (inclusive of today) whose end is still ahead.

    Returns ``{"start_utc", "end_utc", "weekday"}`` or None if nothing is found
    within ``within_days`` (cannot happen for a validated non-empty snapshot).
    Intervals are compared on the UTC axis so DST gaps/repeats stay consistent.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(snapshot["timezone"])
    today = now_utc.astimezone(zone).date()
    for offset in range(within_days + 1):
        day = today + timedelta(days=offset)
        if day.weekday() not in snapshot["weekdays"]:
            continue
        start_utc, end_utc = _day_bounds(snapshot, day, zone)
        if end_utc > now_utc:
            return {
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "weekday": day.weekday(),
            }
    return None
