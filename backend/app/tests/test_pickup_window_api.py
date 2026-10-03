"""取货窗 API 行为测例：拒发、窗外核销状态不变、认领不卡窗、快照不被默认窗改写。"""
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import db_path
from app.main import app

# 2026-01-05 周一 12:00 UTC = 上海周一 20:00；种子默认窗 每天 09:00–21:00（上海墙钟）
FIXED = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.main.now", lambda: FIXED)
    with TestClient(app) as c:
        yield c


def _create(client, **kw):
    r = client.post("/api/wishes", json={"title": "t", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_claim_not_gated_fulfill_gated_status_unchanged(client):
    # 窗：周三 09:00–18:00；当前=上海周一 20:00 → 窗外
    wid = _create(client, window={"days": [2], "start": "09:00", "end": "18:00"})
    r = client.post(f"/api/wishes/{wid}/claim", json={"claimer": "a"})
    assert r.status_code == 200  # 拍板：认领不卡窗，窗外也可锁定
    r = client.post(f"/api/wishes/{wid}/fulfill")
    assert r.status_code == 409 and r.json()["detail"] == "outside_pickup_window"
    w = client.get(f"/api/wishes/{wid}").json()
    assert w["status"] == "claimed"  # 窗外核销失败，状态不变
    assert w["window_open"] is False and w["window_label"] == "周三 09:00–18:00"


def test_fulfill_inside_window_ok(client):
    wid = _create(client)  # 默认窗 每天 09:00–21:00，当前窗内
    client.post(f"/api/wishes/{wid}/claim", json={"claimer": "a"})
    r = client.post(f"/api/wishes/{wid}/fulfill")
    assert r.status_code == 200 and r.json()["status"] == "fulfilled"


def test_create_rejects_bad_window(client):
    for body, code in [
        ({"days": [0], "start": "10:00", "end": "10:00"}, "end_not_after_start"),  # 结束=开始
        ({"days": [0], "start": "10:00", "end": "09:00"}, "end_not_after_start"),  # 结束<开始
        ({"days": [], "start": "09:00", "end": "10:00"}, "empty_days"),
    ]:
        r = client.post("/api/wishes", json={"title": "t", "window": body})
        assert r.status_code == 400 and r.json()["detail"] == code


def test_default_window_change_does_not_rewrite_snapshot(client):
    wid = _create(client, window={"days": [0, 1, 2, 3, 4, 5, 6], "start": "09:00", "end": "19:00"})
    client.post(f"/api/wishes/{wid}/claim", json={"claimer": "a"})
    r = client.put("/api/settings/window",
                   json={"days": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "24:00"})
    assert r.status_code == 200
    w = client.get(f"/api/wishes/{wid}").json()
    assert w["window_label"] == "每天 09:00–19:00"  # 快照不被新默认窗改写
    assert w["window_open"] is False                # 上海 20:00 仍在快照窗外
    r = client.post(f"/api/wishes/{wid}/fulfill")
    assert r.status_code == 409  # 门禁按快照判定，不按新默认窗


def test_legacy_row_without_snapshot_follows_default(client):
    c = sqlite3.connect(db_path())
    cur = c.execute("INSERT INTO wishes(title,note,status,data_quality) VALUES ('老愿望','','open','clean')")
    c.commit(); wid = cur.lastrowid; c.close()
    w = client.get(f"/api/wishes/{wid}").json()
    assert w["window_label"] == "每天 09:00–21:00" and w["window_open"] is True
    client.put("/api/settings/window", json={"days": [2], "start": "09:00", "end": "18:00"})
    w = client.get(f"/api/wishes/{wid}").json()
    assert w["window_open"] is False  # 无快照老数据跟随新默认窗（只读回落，不回写）


def test_put_window_validates(client):
    r = client.put("/api/settings/window", json={"days": [0], "start": "10:00", "end": "10:00"})
    assert r.status_code == 400 and r.json()["detail"] == "end_not_after_start"
    r = client.put("/api/settings/window",
                   json={"days": [0], "start": "09:00", "end": "10:00", "tz": "Mars/Olympus"})
    assert r.status_code == 400 and r.json()["detail"] == "bad_timezone"


def test_rules_pin_three_way_wording(client):
    r = client.get("/api/rules").json()
    assert "认领不卡窗" in r["pickup_claim"]
    assert "状态不变" in r["pickup_fulfill"]
    assert "本地墙钟" in r["pickup_clock"] and "不按 UTC" in r["pickup_clock"]
    assert "不改写" in r["pickup_snapshot"]
