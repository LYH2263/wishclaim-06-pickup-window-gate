from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired
from app.modules.pickup_window import (
    WindowError, attach, default_window, is_open, parse_window, resolve_snapshot,
    snapshot_for_create, to_dict, window_label,
)

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def ttl():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone(); c.close()
    return int(row["value"] if row else 86400)

def read_settings(c) -> dict:
    return {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}

def sweep(c):
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], now())
        if rel:
            c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                      (rel["status"], None, None, None, r["id"]))

def with_window(rows, settings) -> list:
    """给愿望行挂取货窗投影；快照只读，老数据（无快照）回落当前默认窗。"""
    return [attach(r, resolve_snapshot(r.get("window_json"), settings), now()) for r in rows]

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c); c.commit()
    s = read_settings(c)
    rows = with_window([dict(r) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")], s)
    c.close(); return rows

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    row = with_window([dict(r)], read_settings(c))[0]; c.close(); return row

class WishIn(BaseModel):
    title: str
    note: str = ""
    window: dict | None = None  # 可选覆盖默认取货窗（days/start/end）

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    try:
        snap = snapshot_for_create(read_settings(c), body.window)
    except WindowError as e:
        c.close(); raise HTTPException(400, str(e) or "bad_window")
    cur = c.execute("INSERT INTO wishes(title,note,status,data_quality,window_json) VALUES (?,?,?,?,?)",
                    (body.title, body.note, "open", "clean", snap))
    c.commit(); wid = cur.lastrowid; c.close(); return {"id": wid}

class ClaimIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    # 拍板：认领不卡取货窗，窗外也可锁定；卡窗的是核销（fulfill）。
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    allowed = claim_allowed(r["status"], r["claimer"], now(), r["expires_at"])
    if not allowed["ok"]:
        c.close(); raise HTTPException(409, allowed["reason"])
    p = lock_payload(body.claimer, now(), ttl())
    c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
              (p["status"], p["claimer"], p["claimed_at"], p["expires_at"], wid))
    c.commit(); c.close(); return p

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    c.execute("UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "released"}

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "need_claim")
    win = resolve_snapshot(r["window_json"], read_settings(c))
    if not is_open(win, now()):
        c.close(); raise HTTPException(409, "outside_pickup_window")  # 状态不变，等窗内再核销
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "fulfilled"}

@app.get("/api/mine")
def mine(claimer: str):
    c = connect(); sweep(c); c.commit()
    s = read_settings(c)
    rows = with_window([dict(r) for r in c.execute("SELECT * FROM wishes WHERE claimer=?", (claimer,))], s)
    c.close(); return rows

@app.get("/api/done")
def done():
    c = connect()
    rows = with_window([dict(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled'")],
                       read_settings(c))
    c.close(); return rows

@app.get("/api/settings")
def settings():
    c = connect(); rows = read_settings(c); c.close(); return rows

class WindowIn(BaseModel):
    days: list[int]
    start: str
    end: str
    tz: str | None = None

@app.put("/api/settings/window")
def put_window(body: WindowIn):
    """改默认取货窗。只写 settings，不回写已发布愿望的窗快照。"""
    c = connect()
    s = read_settings(c)
    tz = body.tz or s.get("pickup_timezone", "Asia/Shanghai")
    try:
        win = parse_window({"days": body.days, "start": body.start, "end": body.end, "tz": tz})
    except WindowError as e:
        c.close(); raise HTTPException(400, str(e) or "bad_window")
    c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('pickup_days',?)",
              (",".join(str(d) for d in win.days),))
    c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('pickup_start',?)",
              (f"{win.start // 60:02d}:{win.start % 60:02d}",))
    c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('pickup_end',?)",
              (f"{win.end // 60:02d}:{win.end % 60:02d}",))
    c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('pickup_timezone',?)", (win.tz,))
    c.commit(); c.close()
    return {"ok": True, "window": to_dict(win)}

@app.get("/api/rules")
def rules():
    c = connect(); s = read_settings(c); c.close()
    win = parse_window(default_window(s))
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
        "pickup_window": f"默认取货窗：{window_label(win)}（{win.tz} 本地墙钟）；发愿望时可覆盖，发布后落窗快照",
        "pickup_claim": "认领不卡窗：取货窗外也可认领锁定",
        "pickup_fulfill": "核销卡窗：取货窗外核销失败且状态不变，等窗内再核销",
        "pickup_clock": f"取货窗时刻按 {win.tz} 本地墙钟解释，不按 UTC；边界含开始时刻、不含结束时刻",
        "pickup_snapshot": "事后改默认窗不改写已发布愿望的窗快照",
    }
