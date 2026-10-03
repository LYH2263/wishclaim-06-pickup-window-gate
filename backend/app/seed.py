from app.db import connect
from app.modules.pickup_window import DEFAULT_WINDOW, snapshot_for_create


def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wishes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
      claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(wishes)")}
    if "window_json" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN window_json TEXT")
    for key, value in _default_settings().items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (key, value))
    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        snap = snapshot_for_create(_default_settings(), None)
        c.executemany(
            "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality,window_json)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [
                ("机械键盘", "红轴", "open", None, None, None, "clean", snap),
                ("围巾", "羊毛", "open", None, None, None, "clean", snap),
                ("脏愿望-空标题", "", "open", None, None, None, "dirty", None),
                ("过期锁样例", "应被TTL释放", "claimed", "ghost", "2020-01-01T00:00:00+00:00",
                 "2020-01-01T01:00:00+00:00", "dirty", None),
            ],
        )
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('ttl_seconds','86400')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('wall_title','暖粉愿望墙')")
    c.commit()
    c.close()


def _default_settings() -> dict:
    return {
        "pickup_days": ",".join(str(d) for d in DEFAULT_WINDOW["days"]),
        "pickup_start": DEFAULT_WINDOW["start"],
        "pickup_end": DEFAULT_WINDOW["end"],
        "pickup_timezone": DEFAULT_WINDOW["tz"],
    }
