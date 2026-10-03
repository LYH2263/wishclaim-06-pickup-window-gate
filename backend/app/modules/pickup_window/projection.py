"""Pickup-window projection: Chinese human text and frontend-ready state."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.engines import pickup_window as pw

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def human_weekdays(weekdays: list[int]) -> str:
    return "、".join(WEEKDAY_CN[d] for d in sorted(weekdays))


def human_hours(start_hour: int, end_hour: int) -> str:
    if start_hour == 0 and end_hour == 24:
        return "全天"
    return f"{start_hour:02d}:00–{end_hour:02d}:00"


def describe(snapshot: dict) -> str:
    return (
        f"{human_weekdays(snapshot['weekdays'])} {human_hours(snapshot['start_hour'], snapshot['end_hour'])}"
        f"（{snapshot['timezone']} · 按本地墙钟判定）"
    )


def _local_label(dt_utc_iso: str, tzname: str, *, weekday_prefix: bool = True) -> str:
    dt = datetime.fromisoformat(dt_utc_iso).astimezone(ZoneInfo(tzname))
    day = WEEKDAY_CN[dt.weekday()] if weekday_prefix else ""
    return f"{day} {dt.hour:02d}:{dt.minute:02d}".strip()


def project(snapshot: dict, now_utc) -> dict:
    open_now = pw.is_open(snapshot, now_utc)
    nxt = pw.next_opening(snapshot, now_utc)
    local_now = pw.to_local(snapshot, now_utc)
    human = f"{human_weekdays(snapshot['weekdays'])} {human_hours(snapshot['start_hour'], snapshot['end_hour'])}"

    if open_now:
        return {
            "is_open": True,
            "human": human,
            "timezone": snapshot["timezone"],
            "local_now": local_now.isoformat(),
            "opened_at_utc": nxt["start_utc"],
            "closes_at_utc": nxt["end_utc"],
            "next_open_utc": nxt["start_utc"],
            "next_open_local": _local_label(nxt["start_utc"], snapshot["timezone"]),
            "closes_local": _local_label(nxt["end_utc"], snapshot["timezone"], weekday_prefix=False),
        }
    return {
        "is_open": False,
        "human": human,
        "timezone": snapshot["timezone"],
        "local_now": local_now.isoformat(),
        "opened_at_utc": None,
        "closes_at_utc": None,
        "next_open_utc": nxt["start_utc"] if nxt else None,
        "next_open_local": _local_label(nxt["start_utc"], snapshot["timezone"]) if nxt else None,
        "closes_local": None,
    }


def blocked_detail(snapshot: dict, now_utc) -> dict:
    state = project(snapshot, now_utc)
    message = (
        f"当前不在取货时间窗内：{describe(snapshot)}"
        f"；下次开窗：{state['next_open_local'] or '未知'}"
    )
    return {"code": "outside_pickup_window", "message": message, "window": snapshot, "state": state}
