"""取货窗三模块测例：判定 check / 快照 snapshot / 投影 projection。"""
import json
from datetime import datetime, timezone

import pytest

from app.modules.pickup_window.check import WindowError, is_open, parse_window, to_dict
from app.modules.pickup_window.projection import attach, project, window_label
from app.modules.pickup_window.snapshot import (
    default_window, resolve_snapshot, snapshot_for_create,
)

# 2026-01-05 是周一；Asia/Shanghai = UTC+8
MON_0900_SH = datetime(2026, 1, 5, 1, 0, tzinfo=timezone.utc)    # 上海周一 09:00
MON_1759_SH = datetime(2026, 1, 5, 9, 59, tzinfo=timezone.utc)   # 上海周一 17:59
MON_1800_SH = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)   # 上海周一 18:00
SAT_1000_SH = datetime(2026, 1, 10, 2, 0, tzinfo=timezone.utc)   # 上海周六 10:00
MON_1630_UTC = datetime(2026, 1, 5, 16, 30, tzinfo=timezone.utc) # 上海周二 00:30

SETTINGS = {"pickup_days": "0,1,2,3,4", "pickup_start": "09:00",
            "pickup_end": "18:00", "pickup_timezone": "Asia/Shanghai"}
WEEKDAY_9_18 = {"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "18:00",
                "tz": "Asia/Shanghai"}


# ---------- 判定 check ----------

def test_parse_normalizes_days():
    w = parse_window({"days": [4, 0, 4, 2], "start": "09:00", "end": "18:00",
                      "tz": "Asia/Shanghai"})
    assert w.days == (0, 2, 4) and to_dict(w)["start"] == "09:00"

def test_end_not_after_start_rejected():
    for end in ("09:00", "08:59"):  # 结束≤开始
        with pytest.raises(WindowError) as e:
            parse_window({"days": [0], "start": "09:00", "end": end, "tz": "Asia/Shanghai"})
        assert str(e.value) == "end_not_after_start"

def test_bad_window_definitions_rejected():
    for bad, code in [
        ({"days": [], "start": "09:00", "end": "18:00", "tz": "Asia/Shanghai"}, "empty_days"),
        ({"days": [7], "start": "09:00", "end": "18:00", "tz": "Asia/Shanghai"}, "bad_days"),
        ({"days": [0], "start": "9点", "end": "18:00", "tz": "Asia/Shanghai"}, "bad_time_format"),
        ({"days": [0], "start": "09:00", "end": "18:00", "tz": "Mars/Olympus"}, "bad_timezone"),
    ]:
        with pytest.raises(WindowError) as e:
            parse_window(bad)
        assert str(e.value) == code

def test_end_may_be_2400_but_start_may_not():
    w = parse_window({"days": [0], "start": "00:00", "end": "24:00", "tz": "Asia/Shanghai"})
    assert w.end == 1440
    with pytest.raises(WindowError):
        parse_window({"days": [0], "start": "24:00", "end": "24:00", "tz": "Asia/Shanghai"})

def test_is_open_boundaries_start_inclusive_end_exclusive():
    w = parse_window(WEEKDAY_9_18)
    assert is_open(w, MON_0900_SH) is True   # 开始时刻含
    assert is_open(w, MON_1759_SH) is True
    assert is_open(w, MON_1800_SH) is False  # 结束时刻不含

def test_is_open_weekday_set():
    w = parse_window(WEEKDAY_9_18)
    assert is_open(w, SAT_1000_SH) is False  # 周六不在星期集合内

def test_local_wall_clock_not_utc():
    # 同一 UTC 时刻：上海已是周二 00:30，UTC 还是周一 16:30
    w_sh = parse_window({"days": [1], "start": "00:00", "end": "01:00", "tz": "Asia/Shanghai"})
    w_utc = parse_window({"days": [1], "start": "00:00", "end": "01:00", "tz": "UTC"})
    assert is_open(w_sh, MON_1630_UTC) is True    # 按上海本地墙钟：周二 00:30，在窗内
    assert is_open(w_utc, MON_1630_UTC) is False  # 若按 UTC：周一 16:30，在窗外


# ---------- 快照 snapshot ----------

def test_default_window_from_settings():
    assert default_window(SETTINGS) == WEEKDAY_9_18

def test_snapshot_defaults_and_override():
    snap = json.loads(snapshot_for_create(SETTINGS, None))
    assert snap == WEEKDAY_9_18
    snap = json.loads(snapshot_for_create(SETTINGS, {"days": [5, 6], "start": "10:00"}))
    assert snap["days"] == [5, 6] and snap["start"] == "10:00"
    assert snap["end"] == "18:00" and snap["tz"] == "Asia/Shanghai"  # 未覆盖项落默认值

def test_snapshot_override_end_not_after_start_rejected():
    with pytest.raises(WindowError):
        snapshot_for_create(SETTINGS, {"start": "18:00", "end": "18:00"})

def test_default_change_does_not_rewrite_snapshot():
    snap = snapshot_for_create(SETTINGS, None)  # 落快照：工作日 09:00–18:00
    new_settings = {**SETTINGS, "pickup_start": "00:00", "pickup_end": "24:00"}
    w = resolve_snapshot(snap, new_settings)
    assert (w.start, w.end) == (9 * 60, 18 * 60)  # 快照不被新默认窗改写

def test_resolve_falls_back_for_legacy_and_corrupt():
    w = resolve_snapshot(None, SETTINGS)  # 老数据无快照 → 跟随当前默认窗
    assert (w.start, w.end) == (9 * 60, 18 * 60)
    w = resolve_snapshot("{oops", SETTINGS)  # 快照损坏 → 回落默认窗
    assert (w.start, w.end) == (9 * 60, 18 * 60)


# ---------- 投影 projection ----------

def test_project_open_and_closed():
    w = parse_window(WEEKDAY_9_18)
    p = project(w, MON_0900_SH)
    assert p["window_open"] is True and p["window_label"] == "周一至周五 09:00–18:00"
    assert "可核销" in p["window_text"]
    p = project(w, SAT_1000_SH)
    assert p["window_open"] is False and "可认领" in p["window_text"]

def test_window_label_days():
    w = parse_window({"days": [0, 1, 2, 3, 4, 5, 6], "start": "09:00", "end": "21:00",
                      "tz": "Asia/Shanghai"})
    assert window_label(w) == "每天 09:00–21:00"
    w = parse_window({"days": [0, 2], "start": "09:00", "end": "21:00", "tz": "Asia/Shanghai"})
    assert window_label(w) == "周一·周三 09:00–21:00"

def test_attach_keeps_row_fields():
    row = {"id": 1, "title": "键盘", "status": "open"}
    out = attach(row, parse_window(WEEKDAY_9_18), MON_0900_SH)
    assert out["title"] == "键盘" and out["window_open"] is True
