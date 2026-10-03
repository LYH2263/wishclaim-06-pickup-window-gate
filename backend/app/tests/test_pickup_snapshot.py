import json
import sqlite3

import pytest

from app.db import db_path
from app import seed
from app.engines.pickup_window import WindowError
from app.modules.pickup_window import snapshot as S


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_dumps_loads_roundtrip_and_guards():
    s = S.default_snapshot()
    assert S.loads(S.dumps(s)) == s
    assert S.loads(None) is None
    assert S.loads("not json") is None
    assert S.loads(json.dumps([1, 2])) is None


def test_load_rules_falls_back_when_keys_missing(c):
    c.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    c.commit()
    rules = S.load_rules(c)
    assert rules["window"] == S.DEFAULT_WINDOW
    assert rules["timezone"] == S.DEFAULT_TIMEZONE


def test_load_rules_reads_saved(c):
    c.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    c.execute("INSERT INTO settings VALUES(?,?)", (S.SET_WINDOW_KEY, json.dumps({"weekdays": [0], "start_hour": 8, "end_hour": 20})))
    c.execute("INSERT INTO settings VALUES(?,?)", (S.SET_TZ_KEY, "Asia/Tokyo"))
    c.commit()
    rules = S.load_rules(c)
    assert rules["window"]["weekdays"] == [0] and rules["timezone"] == "Asia/Tokyo"


def test_load_rules_corrupt_rows_fall_back(c):
    c.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    c.execute("INSERT INTO settings VALUES(?,?)", (S.SET_WINDOW_KEY, "{bad"))
    c.execute("INSERT INTO settings VALUES(?,?)", (S.SET_TZ_KEY, "Mars/Fake"))
    c.commit()
    rules = S.load_rules(c)
    assert rules["window"] == S.DEFAULT_WINDOW and rules["timezone"] == S.DEFAULT_TIMEZONE


def test_save_rules_upserts_and_rejects_bad(c):
    c.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    c.commit()
    out = S.save_rules(c, {"weekdays": [1, 3], "start_hour": 10, "end_hour": 12}, "UTC")
    c.commit()
    assert out["timezone"] == "UTC"
    # 再存一次不产生重复键，且值被更新
    S.save_rules(c, {"weekdays": [6], "start_hour": 0, "end_hour": 24}, "UTC")
    c.commit()
    n = c.execute("SELECT COUNT(*) n FROM settings").fetchone()["n"]
    assert n == 2
    raw = c.execute("SELECT value FROM settings WHERE key=?", (S.SET_WINDOW_KEY,)).fetchone()["value"]
    assert json.loads(raw)["weekdays"] == [6]
    with pytest.raises(WindowError):
        S.save_rules(c, {"weekdays": [0], "start_hour": 18, "end_hour": 9}, "UTC")
    with pytest.raises(WindowError):
        S.save_rules(c, {"weekdays": [0], "start_hour": 1, "end_hour": 2}, "Mars/Fake")


def test_build_snapshot_defaults_and_partial_override():
    snap = S.build_snapshot(None, S.DEFAULT_WINDOW, S.DEFAULT_TIMEZONE)
    assert snap == {"version": 1, "weekdays": [5, 6], "start_hour": 9, "end_hour": 18, "timezone": "Asia/Shanghai"}
    # 部分覆盖：只给小时，weekdays 回落默认
    snap2 = S.build_snapshot({"start_hour": 8, "end_hour": 20}, S.DEFAULT_WINDOW, S.DEFAULT_TIMEZONE)
    assert snap2["weekdays"] == [5, 6] and (snap2["start_hour"], snap2["end_hour"]) == (8, 20)
    # 时区可愿望级覆盖
    snap3 = S.build_snapshot({"timezone": "Asia/Tokyo"}, S.DEFAULT_WINDOW, S.DEFAULT_TIMEZONE)
    assert snap3["timezone"] == "Asia/Tokyo"


def test_build_snapshot_rejects_semantic_errors():
    with pytest.raises(WindowError):
        S.build_snapshot({"start_hour": 20, "end_hour": 8}, S.DEFAULT_WINDOW, S.DEFAULT_TIMEZONE)


def test_snapshot_isolation_after_rules_change(c):
    """已落窗快照事后不得被默认窗/时区改写。"""
    c.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    c.commit()
    rules_a = S.load_rules(c)
    snap_a = S.build_snapshot(None, rules_a["window"], rules_a["timezone"])
    c.execute("CREATE TABLE wishes(id INTEGER PRIMARY KEY, pickup_window TEXT)")
    c.execute("INSERT INTO wishes(id, pickup_window) VALUES(1,?)", (S.dumps(snap_a),))
    c.commit()
    # 事后改默认窗 + 时区
    S.save_rules(c, {"weekdays": [0], "start_hour": 3, "end_hour": 4}, "UTC")
    c.commit()
    frozen = S.loads(c.execute("SELECT pickup_window FROM wishes WHERE id=1").fetchone()["pickup_window"])
    assert frozen == snap_a
    assert frozen["timezone"] == "Asia/Shanghai" and frozen["weekdays"] == [5, 6]


def test_seed_migration_from_old_schema(tmp_path, monkeypatch):
    db = tmp_path / "wishclaim.db"
    old = sqlite3.connect(db)
    old.executescript("""
    CREATE TABLE wishes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
      claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT
    );
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO wishes(title,status,claimer,claimed_at,expires_at,data_quality)
      VALUES ('老愿望','claimed','ghost','2020-01-01T00:00:00+00:00','2020-01-01T01:00:00+00:00','dirty');
    INSERT INTO settings(key,value) VALUES ('ttl_seconds','86400');
    """)
    old.commit(); old.close()

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    migrated = sqlite3.connect(db)
    migrated.row_factory = sqlite3.Row
    cols = [r["name"] for r in migrated.execute("PRAGMA table_info(wishes)")]
    assert "pickup_window" in cols
    row = migrated.execute("SELECT pickup_window FROM wishes WHERE title='老愿望'").fetchone()
    snap = json.loads(row["pickup_window"])
    assert snap["weekdays"] == [5, 6] and snap["timezone"] == "Asia/Shanghai" and snap["version"] == 1
    keys = {r["key"] for r in migrated.execute("SELECT key FROM settings")}
    assert S.SET_WINDOW_KEY in keys and S.SET_TZ_KEY in keys
    assert migrated.execute("SELECT COUNT(*) n FROM wishes").fetchone()["n"] == 1
    migrated.close()

    # 再跑一次幂等：不新增行、不改快照
    seed.init_db()
    again = sqlite3.connect(db)
    again.row_factory = sqlite3.Row
    assert again.execute("SELECT COUNT(*) n FROM wishes").fetchone()["n"] == 1
    frozen_again = json.loads(again.execute("SELECT pickup_window FROM wishes WHERE id=1").fetchone()["pickup_window"])
    assert frozen_again == snap
    again.close()


def test_seed_fresh_db_seeds_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT pickup_window FROM wishes").fetchall()
    assert len(rows) == 4
    assert all(json.loads(r["pickup_window"])["timezone"] == "Asia/Shanghai" for r in rows)
    conn.close()
