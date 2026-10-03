"""取货窗投影：把窗 + 当前时刻投影成墙/详情/规则三路共用的展示字段。"""
from datetime import datetime

from app.modules.pickup_window.check import DAY_NAMES, Window, is_open


def days_label(days) -> str:
    days = tuple(days)
    if len(days) == 7:
        return "每天"
    parts, i = [], 0
    while i < len(days):
        j = i
        while j + 1 < len(days) and days[j + 1] == days[j] + 1:
            j += 1
        parts.append(DAY_NAMES[days[i]] if i == j else f"{DAY_NAMES[days[i]]}至{DAY_NAMES[days[j]]}")
        i = j + 1
    return "·".join(parts)


def window_label(w: Window) -> str:
    fmt = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    return f"{days_label(w.days)} {fmt(w.start)}–{fmt(w.end)}"


def project(w: Window, moment: datetime) -> dict:
    """三路同钉的同一份口径：认领不卡窗，核销卡窗，窗外核销状态不变。"""
    open_now = is_open(w, moment)
    return {
        "window_open": open_now,
        "window_label": window_label(w),
        "window_tz": w.tz,
        "window_text": "取货窗开放中，可核销" if open_now else "取货窗未开放·可认领，核销需等窗内",
    }


def attach(row: dict, w: Window, moment: datetime) -> dict:
    return {**row, **project(w, moment)}
