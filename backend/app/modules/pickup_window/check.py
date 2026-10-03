"""取货窗判定：解析、校验、开窗判断。

窗 = 星期集合 + 小时段。时刻不按 UTC 解释：先把时刻换算到窗自带时区
（IANA）的本地墙钟，再比星期与墙钟分钟。
边界：start 含、end 不含（09:00–12:00 表示 09:00 在窗内、12:00 在窗外）。
"""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class WindowError(ValueError):
    """取货窗定义非法（结束≤开始、星期为空、时刻/时区格式错）。"""


DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True)
class Window:
    days: tuple  # 0=周一 … 6=周日，非空
    start: int   # 每日开窗分钟（本地墙钟，含）
    end: int     # 每日关窗分钟（本地墙钟，不含；1440 = 当日末尾）
    tz: str      # IANA 时区；窗按该时区本地墙钟解释，不按 UTC


def _parse_hhmm(value, *, allow_2400: bool = False) -> int:
    if not isinstance(value, str) or ":" not in value:
        raise WindowError("bad_time_format")
    hh, _, mm = value.partition(":")
    try:
        h, m = int(hh), int(mm)
    except ValueError:
        raise WindowError("bad_time_format")
    if h < 0 or m < 0 or m > 59:
        raise WindowError("bad_time_format")
    minutes = h * 60 + m
    if minutes > MINUTES_PER_DAY or (minutes == MINUTES_PER_DAY and not allow_2400):
        raise WindowError("bad_time_format")
    return minutes


def parse_window(obj: dict) -> Window:
    """校验并规范化窗定义；结束≤开始、星期为空等一律 WindowError。"""
    if not isinstance(obj, dict):
        raise WindowError("bad_window")
    raw_days = obj.get("days")
    if not isinstance(raw_days, (list, tuple)) or not raw_days:
        raise WindowError("empty_days")
    try:
        days = tuple(sorted({int(d) for d in raw_days}))
    except (TypeError, ValueError):
        raise WindowError("bad_days")
    if any(d < 0 or d > 6 for d in days):
        raise WindowError("bad_days")
    start = _parse_hhmm(obj.get("start"))
    end = _parse_hhmm(obj.get("end"), allow_2400=True)
    if end <= start:
        raise WindowError("end_not_after_start")
    tz = obj.get("tz") or "UTC"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise WindowError("bad_timezone")
    return Window(days=days, start=start, end=end, tz=tz)


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_dict(w: Window) -> dict:
    return {"days": list(w.days), "start": _fmt(w.start), "end": _fmt(w.end), "tz": w.tz}


def is_open(w: Window, moment: datetime) -> bool:
    """moment（时区感知）是否落在窗内；先换算到窗时区的本地墙钟再判定。"""
    local = moment.astimezone(ZoneInfo(w.tz))
    if local.weekday() not in w.days:
        return False
    minutes = local.hour * 60 + local.minute
    return w.start <= minutes < w.end
