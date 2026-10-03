"""取货窗快照：发布愿望时落窗；事后改默认窗不回写已落快照。"""
import json

from app.modules.pickup_window.check import Window, WindowError, parse_window, to_dict

DEFAULT_WINDOW = {"days": [0, 1, 2, 3, 4, 5, 6], "start": "09:00", "end": "21:00",
                  "tz": "Asia/Shanghai"}


def default_window(settings: dict) -> dict:
    """从 settings 读默认窗；缺键回落内置默认。设置本身非法时尽早 WindowError。"""
    raw_days = settings.get("pickup_days")
    if raw_days is None:
        days = list(DEFAULT_WINDOW["days"])
    else:
        try:
            days = [int(d) for d in str(raw_days).split(",") if d.strip() != ""]
        except ValueError:
            days = list(DEFAULT_WINDOW["days"])
    win = {
        "days": days,
        "start": settings.get("pickup_start", DEFAULT_WINDOW["start"]),
        "end": settings.get("pickup_end", DEFAULT_WINDOW["end"]),
        "tz": settings.get("pickup_timezone", DEFAULT_WINDOW["tz"]),
    }
    parse_window(win)
    return win


def snapshot_for_create(settings: dict, override: dict | None) -> str:
    """发布时落窗快照（JSON 串）。override 只覆盖 days/start/end，时区始终
    取发布当下默认窗时区一并落库；结束≤开始等非法窗抛 WindowError → 拒发。"""
    win = default_window(settings)
    if override is not None:
        if not isinstance(override, dict):
            raise WindowError("bad_window")
        for key in ("days", "start", "end"):
            if key in override:
                win[key] = override[key]
    return json.dumps(to_dict(parse_window(win)), ensure_ascii=False, sort_keys=True)


def resolve_snapshot(window_json: str | None, settings: dict) -> Window:
    """读愿望的窗快照；无快照（老数据）或快照损坏时回落当前默认窗。只读，不回写。"""
    if window_json:
        try:
            return parse_window(json.loads(window_json))
        except (json.JSONDecodeError, WindowError):
            pass
    return parse_window(default_window(settings))
