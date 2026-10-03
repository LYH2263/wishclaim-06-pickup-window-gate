from app.db import connect
from app.modules.pickup_window import snapshot as pw_snap


def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wishes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
      claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT,
      pickup_window TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    # 旧库迁移：CREATE IF NOT EXISTS 不会补列
    cols = [r["name"] for r in c.execute("PRAGMA table_info(wishes)")]
    if "pickup_window" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN pickup_window TEXT")
    # 默认取货窗设置（不覆盖已改值）
    for key, value in (
        (pw_snap.SET_WINDOW_KEY, pw_snap.dumps(pw_snap.DEFAULT_WINDOW)),
        (pw_snap.SET_TZ_KEY, pw_snap.DEFAULT_TIMEZONE),
    ):
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
    # 回填：每个愿望冻结当前默认窗快照；只填 NULL，重复启动幂等
    backfill = pw_snap.dumps(pw_snap.default_snapshot())
    c.execute("UPDATE wishes SET pickup_window=? WHERE pickup_window IS NULL", (backfill,))
    c.commit()
    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        c.executemany(
            "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality,pickup_window) VALUES (?,?,?,?,?,?,?,?)",
            [
                ("机械键盘", "红轴", "open", None, None, None, "clean", backfill),
                ("围巾", "羊毛", "open", None, None, None, "clean", backfill),
                ("脏愿望-空标题", "", "open", None, None, None, "dirty", backfill),
                ("过期锁样例", "应被TTL释放", "claimed", "ghost", "2020-01-01T00:00:00+00:00",
                 "2020-01-01T01:00:00+00:00", "dirty", backfill),
            ],
        )
        c.execute("INSERT INTO settings(key,value) VALUES ('ttl_seconds','86400')")
        c.execute("INSERT INTO settings(key,value) VALUES ('wall_title','暖粉愿望墙')")
        c.commit()
    c.close()
