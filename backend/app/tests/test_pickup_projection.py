from datetime import datetime, timezone

from app.modules.pickup_window import projection as P

SH = "Asia/Shanghai"
SNAP = {"version": 1, "weekdays": [5, 6], "start_hour": 9, "end_hour": 18, "timezone": SH}


def test_human_weekdays():
    assert P.human_weekdays([6, 5]) == "周六、周日"
    assert P.human_weekdays([0]) == "周一"


def test_human_hours():
    assert P.human_hours(9, 18) == "09:00–18:00"
    assert P.human_hours(0, 24) == "全天"


def test_describe_literal():
    assert P.describe(SNAP) == "周六、周日 09:00–18:00（Asia/Shanghai · 按本地墙钟判定）"


def test_project_when_open():
    # 2026-01-03 周六 10:00 上海
    now = datetime(2026, 1, 3, 2, 0, tzinfo=timezone.utc)
    st = P.project(SNAP, now)
    assert st["is_open"] is True
    assert st["human"] == "周六、周日 09:00–18:00"
    assert st["opened_at_utc"] is not None and st["closes_at_utc"] is not None
    assert st["closes_local"] == "18:00"
    assert st["next_open_local"] == "周六 09:00"
    assert st["local_now"].endswith("+08:00")


def test_project_when_closed():
    # 2026-01-07 周三 10:00 上海
    now = datetime(2026, 1, 7, 2, 0, tzinfo=timezone.utc)
    st = P.project(SNAP, now)
    assert st["is_open"] is False
    assert st["opened_at_utc"] is None and st["closes_at_utc"] is None
    assert st["next_open_local"] == "周六 09:00"
    assert st["closes_local"] is None


def test_blocked_detail_shape():
    now = datetime(2026, 1, 7, 2, 0, tzinfo=timezone.utc)
    d = P.blocked_detail(SNAP, now)
    assert set(d.keys()) == {"code", "message", "window", "state"}
    assert d["code"] == "outside_pickup_window"
    assert "周六、周日 09:00–18:00" in d["message"]
    assert "下次开窗：周六 09:00" in d["message"]
