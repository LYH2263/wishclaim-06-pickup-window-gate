from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app import seed
from app.db import connect
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired
from app.engines.pickup_window import WindowError as PickupWindowError
from app.engines import pickup_window as pw_engine
from app.modules.pickup_window import projection as pw_projection
from app.modules.pickup_window import snapshot as pw_snapshot

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def ttl():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone(); c.close()
    return int(row["value"] if row else 86400)

def sweep(c):
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], now())
        if rel:
            c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                      (rel["status"], None, None, None, r["id"]))

def shape(r):
    return pw_snapshot.attach_state(dict(r), now())

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c); c.commit()
    rows = [shape(r) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]; c.close(); return rows

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    if not r: raise HTTPException(404, "not found")
    return shape(r)

class WindowIn(BaseModel):
    weekdays: list[int] = Field(min_length=1)
    start_hour: int = Field(ge=0, le=24)
    end_hour: int = Field(ge=0, le=24)
    timezone: str | None = None

class WishIn(BaseModel):
    title: str
    note: str = ""
    pickup_window: WindowIn | None = None

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    rules = pw_snapshot.load_rules(c)
    try:
        snap = pw_snapshot.build_snapshot(
            body.pickup_window.model_dump() if body.pickup_window else None,
            rules["window"], rules["timezone"])
    except PickupWindowError as e:
        c.close(); raise HTTPException(400, {"code": "invalid_pickup_window", "errors": e.errors})
    cur = c.execute(
        "INSERT INTO wishes(title,note,status,data_quality,pickup_window) VALUES (?,?,?,?,?)",
        (body.title, body.note, "open", "clean", pw_snapshot.dumps(snap)))
    c.commit(); wid = cur.lastrowid; c.close(); return {"id": wid, "pickup_window": snap}

class ClaimIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
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
    # claim 不卡窗；仅 fulfill 按愿望自身快照卡窗。窗外失败且不得改动 status。
    snap = pw_snapshot.loads(r["pickup_window"])
    if snap is not None and not pw_engine.is_open(snap, now()):
        detail = pw_projection.blocked_detail(snap, now())
        c.close(); raise HTTPException(409, detail)
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "fulfilled"}

@app.get("/api/mine")
def mine(claimer: str):
    c = connect(); sweep(c); c.commit()
    rows = [shape(r) for r in c.execute("SELECT * FROM wishes WHERE claimer=?", (claimer,))]; c.close(); return rows

@app.get("/api/done")
def done():
    c = connect()
    rows = [shape(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled'")]; c.close(); return rows

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

PICKUP_RULE_NOTE = "取货时间窗按所选时区的本地墙钟判定，小时为 24 小时制整点，含起点不含终点；默认窗仅影响此后发布的愿望，已发布愿望按各自快照核销。"

@app.get("/api/rules/pickup-window")
def get_pickup_window_rules():
    c = connect(); rules = pw_snapshot.load_rules(c); c.close()
    return {**rules, "note": PICKUP_RULE_NOTE}

class PickupRulesIn(BaseModel):
    weekdays: list[int] = Field(min_length=1)
    start_hour: int = Field(ge=0, le=24)
    end_hour: int = Field(ge=0, le=24)
    timezone: str

@app.put("/api/rules/pickup-window")
def put_pickup_window_rules(body: PickupRulesIn):
    c = connect()
    try:
        rules = pw_snapshot.save_rules(c, body.model_dump(), body.timezone)
        c.commit()
    except PickupWindowError as e:
        c.rollback(); c.close(); raise HTTPException(400, {"code": "invalid_pickup_window", "errors": e.errors})
    c.close(); return {**rules, "note": PICKUP_RULE_NOTE}

@app.get("/api/rules")
def rules():
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
        "pickup_window": "认领不卡时间窗；核销须在愿望自己的取货窗内（按快照时区的本地墙钟，含起点不含终点），默认窗为周六、周日 09:00–18:00（Asia/Shanghai）",
    }
