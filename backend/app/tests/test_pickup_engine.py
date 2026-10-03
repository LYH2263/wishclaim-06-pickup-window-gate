from datetime import datetime, timezone
import pytest
from zoneinfo import ZoneInfo
from app.engines.pickup_window import WindowError, is_open, next_opening, to_local, validate_window

SH = "Asia/Shanghai"
SNAP = {"version": 1, "weekdays": [5, 6], "start_hour": 9, "end_hour": 18, "timezone": SH}


def local(y, m, d, hh, mm=0, tz=SH):
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(tz))


# ---------- validate_window ----------

def test_validate_normalizes_dedup_and_sort():
    out = validate_window({"weekdays": [6, 5, 5], "start_hour": 9, "end_hour": 18, "timezone": SH})
    assert out["weekdays"] == [5, 6]
    assert out["timezone"] == SH


def test_validate_timezone_optional_by_default():
    out = validate_window({"weekdays": [0], "start_hour": 0, "end_hour": 24})
    assert "timezone" not in out


def test_validate_rejects_end_le_start():
    for s, e in [(9, 9), (18, 9)]:
        with pytest.raises(WindowError) as ei:
            validate_window({"weekdays": [0], "start_hour": s, "end_hour": e})
        assert any("结束小时" in x for x in ei.value.errors)


def test_validate_rejects_out_of_range():
    bad = [
        {"weekdays": [7], "start_hour": 9, "end_hour": 18},
        {"weekdays": [-1], "start_hour": 9, "end_hour": 18},
        {"weekdays": [], "start_hour": 9, "end_hour": 18},
        {"weekdays": [0], "start_hour": 25, "end_hour": 18},
        {"weekdays": [0], "start_hour": 9, "end_hour": -1},
        {"weekdays": [0], "start_hour": 24, "end_hour": 24},
    ]
    for raw in bad:
        with pytest.raises(WindowError):
            validate_window(raw)


def test_validate_all_day_allowed():
    out = validate_window({"weekdays": [0, 1, 2, 3, 4, 5, 6], "start_hour": 0, "end_hour": 24})
    assert out["start_hour"] == 0 and out["end_hour"] == 24


def test_validate_rejects_bad_timezone_and_missing_required():
    with pytest.raises(WindowError):
        validate_window({"weekdays": [0], "start_hour": 1, "end_hour": 2, "timezone": "Mars/Fake"})
    with pytest.raises(WindowError) as ei:
        validate_window({"weekdays": [0], "start_hour": 1, "end_hour": 2}, require_timezone=True)
    assert any("时区必填" in x for x in ei.value.errors)


# ---------- is_open: weekday + half-open segment ----------

def test_is_open_inside():
    assert is_open(SNAP, local(2026, 1, 3, 10)) is True   # 周六 10:00 上海
    assert is_open(SNAP, local(2026, 1, 3, 17, 59)) is True


def test_is_closed_weekday_mismatch_and_edges():
    assert is_open(SNAP, local(2026, 1, 7, 10)) is False   # 周三
    assert is_open(SNAP, local(2026, 1, 3, 8, 59)) is False
    assert is_open(SNAP, local(2026, 1, 3, 9, 0)) is True   # 含起点
    assert is_open(SNAP, local(2026, 1, 3, 18, 0)) is False # 不含终点


def test_is_open_utc_conversion():
    # 上海周六 09:00 == UTC 周六 01:00
    assert is_open(SNAP, datetime(2026, 1, 3, 1, 0, tzinfo=timezone.utc)) is True
    # UTC 周五 23:30 == 上海周六 07:30 -> 关
    assert is_open(SNAP, datetime(2026, 1, 2, 23, 30, tzinfo=timezone.utc)) is False


def test_naive_now_treated_as_utc():
    assert is_open(SNAP, datetime(2026, 1, 3, 1, 0)) is True


def test_to_local_basic():
    lt = to_local(SNAP, datetime(2026, 1, 3, 1, 0, tzinfo=timezone.utc))
    assert lt.hour == 9 and lt.utcoffset().total_seconds() == 8 * 3600


# ---------- next_opening ----------

def test_next_opening_today_when_open():
    n = next_opening(SNAP, local(2026, 1, 3, 10))
    assert n["weekday"] == 5
    assert n["start_utc"].endswith("+00:00")


def test_next_opening_next_day():
    # 周六 19:00 已关 -> 周日 09:00
    n = next_opening(SNAP, local(2026, 1, 3, 19))
    start = datetime.fromisoformat(n["start_utc"]).astimezone(ZoneInfo(SH))
    assert n["weekday"] == 6 and (start.hour, start.minute) == (9, 0)


def test_next_opening_wraps_around_week():
    # 周日 19:00 -> 下周六
    n = next_opening(SNAP, local(2026, 1, 4, 19))
    start = datetime.fromisoformat(n["start_utc"]).astimezone(ZoneInfo(SH))
    assert n["weekday"] == 5 and start.day == 10


def test_next_opening_midweek_picks_nearest():
    # 周三 -> 周六
    n = next_opening(SNAP, local(2026, 1, 7, 12))
    assert n["weekday"] == 5


# ---------- DST ----------

def test_dst_spring_forward_does_not_crash():
    # America/New_York 2026-03-08 春跳，02:00-03:00 这一本地小时不存在
    snap = {"weekdays": [6], "start_hour": 1, "end_hour": 3, "timezone": "America/New_York"}
    at = datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)  # 当地 03:00 EDT（跳完）
    assert is_open(snap, at) is False
    n = next_opening(snap, datetime(2026, 3, 8, 12, tzinfo=timezone.utc))
    assert n is not None and n["weekday"] == 6


def test_dst_fall_back_interval_stays_continuous():
    # 2026-11-01 秋回，01:00 重复；窗 00:30-02:00 在 UTC 轴是一段连续区间
    snap = {"weekdays": [6], "start_hour": 0, "end_hour": 3, "timezone": "America/New_York"}
    assert is_open(snap, datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)) is True  # 当地 02:30 EST
    assert is_open(snap, datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)) is False  # 当地 03:00
