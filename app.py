import csv
import io
import json
import os
import secrets
import time
import urllib.request
import uuid
from collections import defaultdict
from contextlib import closing

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from db import db, init_db

load_dotenv()

# Optional: accept participants straight from LimeSurvey (RemoteControl API, JSON-RPC)
LS_RPC_URL = os.getenv("LS_RPC_URL")  # e.g. https://survey.example.edu/index.php/admin/remotecontrol
LS_USER = os.getenv("LS_USER")
LS_PASSWORD = os.getenv("LS_PASSWORD")
LS_SURVEY_ID = os.getenv("LS_SURVEY_ID")

DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "100"))  # user messages per participant per 24h
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
MODELS = json.load(open("models.json"))

poe = OpenAI(api_key=os.environ["POE_API_KEY"], base_url="https://api.poe.com/v1")

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
    https_only=os.getenv("HTTPS_ONLY") == "1",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
)


init_db()


def _ls_rpc(method: str, params: list):
    req = urllib.request.Request(
        LS_RPC_URL,
        data=json.dumps({"method": method, "params": params, "id": 1}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["result"]


def limesurvey_has_token(token: str) -> bool:
    """True if this participant token exists in the LimeSurvey survey. Never raises."""
    if not (LS_RPC_URL and LS_USER and LS_PASSWORD and LS_SURVEY_ID and token):
        return False
    try:
        key = _ls_rpc("get_session_key", [LS_USER, LS_PASSWORD])
        if not isinstance(key, str):
            return False
        try:
            res = _ls_rpc("list_participants", [key, int(LS_SURVEY_ID), 0, 1, False, False, {"token": token}])
        finally:
            _ls_rpc("release_session_key", [key])
        return isinstance(res, list) and any(str(p.get("token", "")).lower() == token.lower() for p in res)
    except Exception as e:
        print(f"[limesurvey error] {type(e).__name__}: {e}", flush=True)
        return False

# ponytail: in-memory login throttle keyed by client IP; behind a proxy every
# visitor shares one IP, so pass the real IP through (uvicorn --proxy-headers)
FAILS = defaultdict(list)


def me(request: Request) -> str:
    pid = request.session.get("pid")
    if not pid:
        raise HTTPException(401, "Not logged in")
    return pid


def log_event(pid: str | None, type_: str, cid: str | None = None, detail: str | None = None):
    """One row per interaction, so researchers can reconstruct everything a participant did."""
    with closing(db()) as c, c:
        c.execute(
            "INSERT INTO events(participant, type, conversation_id, detail, ts) VALUES (?,?,?,?,?)",
            (pid, type_, cid, detail, time.time()),
        )


class Login(BaseModel):
    identifier: str
    consent: bool


@app.post("/api/login")
def login(b: Login, request: Request):
    ip = request.client.host if request.client else "?"
    now = time.time()
    FAILS[ip] = [t for t in FAILS[ip] if now - t < 600]
    if len(FAILS[ip]) >= 10:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    if not b.consent:
        raise HTTPException(400, "Please confirm that you agree to take part.")
    raw = b.identifier.strip()
    pid = raw.lower()
    with closing(db()) as c, c:
        known = c.execute("SELECT 1 FROM participants WHERE id=?", (pid,)).fetchone()
        if not known and limesurvey_has_token(raw):
            # first visit from LimeSurvey: register the participant automatically
            c.execute("INSERT OR IGNORE INTO participants(id, created_at) VALUES (?,?)", (pid, now))
            known = True
        if not known:
            FAILS[ip].append(now)
            raise HTTPException(401, "Code or email not recognised.")
        c.execute(
            "UPDATE participants SET consented_at=COALESCE(consented_at, ?), last_login=? WHERE id=?",
            (now, now, pid),
        )
    request.session["pid"] = pid
    log_event(pid, "login")
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    log_event(request.session.get("pid"), "logout")
    request.session.clear()
    return {"ok": True}


EVENT_TYPES = {"new_chat", "open_chat", "model_change", "download_chat", "page_view"}


class Event(BaseModel):
    type: str
    conversation_id: str | None = None
    detail: str | None = None


@app.post("/api/event")
def event(b: Event, pid: str = Depends(me)):
    if b.type not in EVENT_TYPES:
        raise HTTPException(400, "Unknown event type")
    log_event(pid, b.type, b.conversation_id, (b.detail or "")[:200] or None)
    return {"ok": True}


@app.get("/api/me")
def whoami(pid: str = Depends(me)):
    return {"participant": pid, "models": MODELS}


@app.get("/api/conversations")
def conversations(pid: str = Depends(me)):
    with closing(db()) as c:
        rows = c.execute(
            """SELECT conversation_id AS id, MIN(ts) AS t,
                      (SELECT content FROM messages m2
                        WHERE m2.conversation_id = m.conversation_id AND m2.role='user'
                        ORDER BY m2.id LIMIT 1) AS title
                 FROM messages m WHERE participant=?
                  AND conversation_id NOT IN
                      (SELECT conversation_id FROM hidden_conversations WHERE participant=?)
                 GROUP BY conversation_id ORDER BY t DESC""",
            (pid, pid),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/conversations/{cid}")
def conversation(cid: str, pid: str = Depends(me)):
    with closing(db()) as c:
        rows = c.execute(
            "SELECT role, content, model FROM messages WHERE participant=? AND conversation_id=? ORDER BY id",
            (pid, cid),
        ).fetchall()
    return [dict(r) for r in rows]


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str, pid: str = Depends(me)):
    # Soft delete: hidden from the participant, kept in the DB for the researchers' export.
    with closing(db()) as c, c:
        c.execute(
            "INSERT OR IGNORE INTO hidden_conversations(participant, conversation_id, ts) VALUES (?,?,?)",
            (pid, cid, time.time()),
        )
    log_event(pid, "delete_chat", cid)
    return {"ok": True}


class Chat(BaseModel):
    conversation_id: str | None = None
    model: str
    message: str


def sse(obj) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.post("/api/chat")
def chat(b: Chat, pid: str = Depends(me)):
    if b.model not in MODELS:
        raise HTTPException(400, "Unknown model")
    msg = b.message.strip()
    if not msg or len(msg) > 8000:
        raise HTTPException(400, "Message must be between 1 and 8000 characters")
    cid = b.conversation_id or uuid.uuid4().hex

    with closing(db()) as c, c:
        used = c.execute(
            "SELECT COUNT(*) FROM messages WHERE participant=? AND role='user' AND ts>?",
            (pid, time.time() - 86400),
        ).fetchone()[0]
        if used >= DAILY_LIMIT:
            raise HTTPException(429, "Daily message limit reached. Please come back tomorrow.")
        history = [
            dict(r)
            for r in c.execute(
                "SELECT role, content FROM messages WHERE participant=? AND conversation_id=? ORDER BY id",
                (pid, cid),
            )
        ]
        c.execute(
            "INSERT INTO messages(participant, conversation_id, model, role, content, ts) VALUES (?,?,?,?,?,?)",
            (pid, cid, b.model, "user", msg, time.time()),
        )
    messages = history + [{"role": "user", "content": msg}]

    def gen():
        t0, parts, err = time.time(), [], None
        yield sse({"cid": cid})
        try:
            stream = poe.chat.completions.create(model=b.model, messages=messages, stream=True)
            for ch in stream:
                d = ch.choices[0].delta.content if ch.choices else None
                if d:
                    parts.append(d)
                    yield sse({"t": d})
        except Exception as e:
            err = type(e).__name__
            print(f"[poe error] model={b.model} {err}: {e}", flush=True)
            yield sse({"error": "The model did not respond. Try again or pick another model."})
        finally:
            # also runs when the browser disconnects mid-stream, so partial replies are kept
            text = "".join(parts)
            if text or err:
                with closing(db()) as c, c:
                    c.execute(
                        "INSERT INTO messages(participant, conversation_id, model, role, content, ts, latency_ms) VALUES (?,?,?,?,?,?,?)",
                        (pid, cid, b.model, "assistant", text or f"[error: {err}]", time.time(), int((time.time() - t0) * 1000)),
                    )
        yield sse({"done": True})

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    )


@app.get("/admin/export.csv")
def export(x_admin_token: str | None = Header(None)):
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(403)
    with closing(db()) as c:
        rows = c.execute(
            "SELECT id, participant, conversation_id, model, role, content, ts, latency_ms FROM messages ORDER BY id"
        ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(rows[0].keys() if rows else ["id", "participant", "conversation_id", "model", "role", "content", "ts", "latency_ms"])
    w.writerows(tuple(r) for r in rows)
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8")


@app.get("/admin/events.csv")
def export_events(x_admin_token: str | None = Header(None)):
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(403)
    cols = ["id", "participant", "type", "conversation_id", "detail", "ts"]
    with closing(db()) as c:
        rows = c.execute(f"SELECT {', '.join(cols)} FROM events ORDER BY id").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerows(tuple(r) for r in rows)
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
