import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from zoneinfo import ZoneInfo

from app import seed
from app.db import connect
from app import main
from app.main import ClaimIn, PickupRulesIn, WishIn, WindowIn
from app.modules.pickup_window import snapshot as S


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    yield


def _today_local_weekday():
    return datetime.now(timezone.utc).astimezone(ZoneInfo(S.DEFAULT_TIMEZONE)).weekday()


def _open_window():
    # 今天本地日 + 全天：此刻必然开窗
    return WindowIn(weekdays=[_today_local_weekday()], start_hour=0, end_hour=24)


def _closed_window():
    # 排除今天的星期集合：此刻必然闭窗
    others = [d for d in range(7) if d != _today_local_weekday()]
    return WindowIn(weekdays=others, start_hour=3, end_hour=4)


def _row(wid):
    c = connect()
    r = dict(c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone())
    c.close()
    return r


def test_claim_succeeds_outside_window_but_fulfill_409_keeps_status():
    created = main.create_wish(WishIn(title="闭窗礼", pickup_window=_closed_window()))
    wid = created["id"]
    # claim 不卡窗：任何时刻都能锁
    p = main.claim(wid, ClaimIn(claimer="alice"))
    assert p["status"] == "claimed"

    with pytest.raises(HTTPException) as ei:
        main.fulfill(wid)
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "outside_pickup_window"
    assert "下次开窗" in ei.value.detail["message"]

    row = _row(wid)
    assert row["status"] == "claimed" and row["claimer"] == "alice"
    assert json.loads(row["pickup_window"])["weekdays"] == _closed_window().weekdays


def test_fulfill_succeeds_inside_window():
    wid = main.create_wish(WishIn(title="开窗礼", pickup_window=_open_window()))["id"]
    main.claim(wid, ClaimIn(claimer="bob"))
    out = main.fulfill(wid)
    assert out["status"] == "fulfilled"
    assert _row(wid)["status"] == "fulfilled"


def test_fulfill_need_claim_check_precedes_window():
    wid = main.create_wish(WishIn(title="没人认领", pickup_window=_open_window()))["id"]
    with pytest.raises(HTTPException) as ei:
        main.fulfill(wid)
    assert ei.value.status_code == 400 and ei.value.detail == "need_claim"
    assert _row(wid)["status"] == "open"


def test_invalid_window_rejected_at_create():
    with pytest.raises(HTTPException) as ei:
        main.create_wish(WishIn(title="坏窗", pickup_window=WindowIn(weekdays=[0], start_hour=18, end_hour=9)))
    assert ei.value.status_code == 400
    assert ei.value.detail["code"] == "invalid_pickup_window"


def test_changing_default_window_does_not_touch_snapshots():
    created = main.create_wish(WishIn(title="先发的", pickup_window=_closed_window()))
    wid = created["id"]
    frozen = dict(created["pickup_window"])

    main.put_pickup_window_rules(
        PickupRulesIn(weekdays=[0], start_hour=3, end_hour=4, timezone="UTC"))

    got = main.get_wish(wid)
    assert got["pickup_window"] == frozen
    assert got["pickup_state"]["timezone"] == frozen["timezone"]
    # 此后新愿望跟随新默认
    later = main.create_wish(WishIn(title="后发的"))
    assert later["pickup_window"]["timezone"] == "UTC"
    assert later["pickup_window"]["weekdays"] == [0]


def test_rules_endpoints_roundtrip():
    body = main.get_pickup_window_rules()
    assert body["timezone"] == "Asia/Shanghai"
    saved = main.put_pickup_window_rules(
        PickupRulesIn(weekdays=[0, 2], start_hour=8, end_hour=20, timezone="Asia/Tokyo"))
    assert saved["window"]["weekdays"] == [0, 2]
    with pytest.raises(HTTPException) as ei:
        main.put_pickup_window_rules(
            PickupRulesIn(weekdays=[0], start_hour=20, end_hour=8, timezone="Asia/Tokyo"))
    assert ei.value.status_code == 400


def test_shapes_attach_pickup_state():
    wid = main.create_wish(WishIn(title="整形", pickup_window=_open_window()))["id"]
    got = main.get_wish(wid)
    assert isinstance(got["pickup_window"], dict)
    assert got["pickup_state"] is not None and got["pickup_state"]["is_open"] is True
    assert any(isinstance(w["pickup_window"], dict) for w in main.list_wishes())


def test_sweep_keeps_snapshot_column():
    # 种子里的 "过期锁样例" 是 2020 年的过期 claimed 锁
    c = connect()
    main.sweep(c)
    c.commit()
    row = c.execute("SELECT status, pickup_window FROM wishes WHERE title='过期锁样例'").fetchone()
    c.close()
    assert row["status"] == "open"
    assert json.loads(row["pickup_window"])["version"] == 1
