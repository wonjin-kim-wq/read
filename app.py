"""읽는 힘 — 비문학 독해 연습: Flask 백엔드.

정적 파일(index.html, assets/)과 지문 데이터(data/passages.json을 시드로 하는 SQLite DB)를
서버에서 제공한다. 외부 API를 호출해야 할 때는 API 키 등 민감한 값을 브라우저에 노출하지 않도록
이 서버(백엔드)에서 호출하고 결과만 클라이언트로 내려준다.

로컬 실행:
    pip install -r requirements.txt
    python3 app.py
    브라우저에서 http://localhost:8000 접속

배포 시에는 플랫폼이 PORT 환경변수를 주입하며, 이 앱은 0.0.0.0에 바인딩한다.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

import question_generator as qg

logging.basicConfig(level=logging.INFO)  # AI 응답 시간·모델 기록을 서버 로그에 남긴다

ROOT_DIR = Path(__file__).resolve().parent
DATA_PATH = ROOT_DIR / "data" / "passages.json"
PASSAGES_DB_PATH = Path(os.environ.get("PASSAGES_DB_PATH", ROOT_DIR / "instance" / "passages.db"))
_passages_db_lock = threading.Lock()

MAX_PDF_BYTES = 5 * 1024 * 1024
MIN_TEXT_CHARS = 200
MAX_TEXT_CHARS = 8000

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_PDF_BYTES + 64 * 1024


def _load_secret_key():
    """세션 쿠키 서명 키. 환경변수로 주지 않으면 instance/에 한 번 만들어 재사용한다.

    (재배포 때마다 바뀌면 로그인한 사용자가 전부 로그아웃되므로 파일로 고정한다.)
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_path = ROOT_DIR / "instance" / "secret_key.txt"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_path.write_text(key, encoding="utf-8")
    return key


app.secret_key = _load_secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# Gemini 키(GEMINI_API_KEY)와 모델(GEMINI_MODEL)은 question_generator가 환경변수에서 읽는다.
# 무료 한도를 넘지 않도록 하루 생성 횟수를 서버에서 제한한다(환경변수로 조정).
#   GENERATE_DAILY_LIMIT_PER_USER: 한 사용자(접속 주소)당 하루 생성 횟수
#   GENERATE_DAILY_LIMIT_TOTAL:    사이트 전체 하루 생성 횟수
USAGE_DB_PATH = Path(os.environ.get("USAGE_DB_PATH", ROOT_DIR / "instance" / "usage.db"))
_db_lock = threading.Lock()


def _int_env(name, default):
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


def limit_per_user():
    return _int_env("GENERATE_DAILY_LIMIT_PER_USER", 3)


def limit_total():
    return _int_env("GENERATE_DAILY_LIMIT_TOTAL", 15)


def _passages_db():
    """지문 데이터를 담는 SQLite DB 연결을 연다.

    `data/passages.json`을 최초 1회 읽어 DB를 채우고, 그 뒤로는 DB를 기준으로
    `/api/passages`를 응답한다. 이미 채워진 DB는 다시 시드하지 않으므로
    (재배포 시 플랫폼이 DB 파일을 그대로 옮겨 주는 한) 운영 중 추가/수정한
    지문이 지워지지 않는다.
    """
    PASSAGES_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(PASSAGES_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS passages ("
        " id TEXT PRIMARY KEY, position INTEGER NOT NULL, data TEXT NOT NULL)"
    )
    count = conn.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
    if count == 0:
        with open(DATA_PATH, encoding="utf-8") as f:
            seed = json.load(f)
        conn.executemany(
            "INSERT OR REPLACE INTO passages (id, position, data) VALUES (?, ?, ?)",
            [(p["id"], i, json.dumps(p, ensure_ascii=False)) for i, p in enumerate(seed)],
        )
        conn.commit()
    return conn


def load_passages():
    with _passages_db_lock, _passages_db() as conn:
        rows = conn.execute("SELECT data FROM passages ORDER BY position").fetchall()
    return [json.loads(row[0]) for row in rows]


@app.get("/api/passages")
def api_passages():
    """지문·문제 데이터를 SQLite DB에서 읽어 내려준다.

    DB는 최초 요청 시 `data/passages.json`을 시드로 자동 생성되며, 이후에는 DB가
    기준이 된다. 프런트엔드(assets/js/app.js)는 이 엔드포인트만 바라보므로
    저장 방식이 바뀌어도 수정이 필요 없다.
    """
    try:
        passages = load_passages()
    except (OSError, json.JSONDecodeError, sqlite3.Error):
        app.logger.exception("failed to load passages")
        return jsonify({"error": "failed to load passages"}), 500
    return jsonify(passages)


# ---------------- 로그인 / 회원가입 ----------------

ACCOUNTS_DB_PATH = Path(os.environ.get("ACCOUNTS_DB_PATH", ROOT_DIR / "instance" / "accounts.db"))
_accounts_db_lock = threading.Lock()
ROLES = ("student", "teacher")
MIN_PASSWORD_LEN = 6
MAX_NAME_LEN = 20


def _accounts_db():
    ACCOUNTS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ACCOUNTS_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " role TEXT NOT NULL,"
        " name TEXT NOT NULL,"
        " password_hash TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " UNIQUE(role, name))"
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "level" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN level TEXT NOT NULL DEFAULT '중학'")
        conn.commit()
    conn.execute("CREATE TABLE IF NOT EXISTS trial_usage (client TEXT PRIMARY KEY, used INTEGER NOT NULL)")
    return conn


def _user_public(row):
    return {"id": row[0], "role": row[1], "name": row[2], "level": row[4] if len(row) > 4 else row[3]}


@app.post("/api/auth/signup")
def auth_signup():
    body = request.get_json(silent=True) or {}
    role = body.get("role")
    name = (body.get("name") or "").strip()
    password = body.get("password") or ""

    level = body.get("level", "중학")
    if level not in qg.LEVELS:
        return jsonify({"error": "학교급을 선택해 주세요."}), 400
    if role not in ROLES:
        return jsonify({"error": "학생 또는 교사를 선택해 주세요."}), 400
    if not name or len(name) > MAX_NAME_LEN:
        return jsonify({"error": f"이름을 1~{MAX_NAME_LEN}자로 입력해 주세요."}), 400
    if len(password) < MIN_PASSWORD_LEN:
        return jsonify({"error": f"비밀번호는 {MIN_PASSWORD_LEN}자 이상으로 만들어 주세요."}), 400

    with _accounts_db_lock, _accounts_db() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE role = ? AND name = ?", (role, name)
        ).fetchone()
        if existing:
            return jsonify({"error": "이미 같은 이름으로 가입되어 있어요. 다른 이름을 써 보세요."}), 409
        conn.execute(
            "INSERT INTO users (role, name, password_hash, created_at, level) VALUES (?, ?, ?, ?, ?)",
            (role, name, generate_password_hash(password, method="pbkdf2:sha256"), datetime.now(timezone.utc).isoformat(), level),
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    session.clear()
    session["user_id"] = user_id
    session.permanent = True
    return jsonify({"user": {"id": user_id, "role": role, "name": name, "level": level}})


@app.post("/api/auth/login")
def auth_login():
    body = request.get_json(silent=True) or {}
    role = body.get("role")
    name = (body.get("name") or "").strip()
    password = body.get("password") or ""

    if role not in ROLES or not name or not password:
        return jsonify({"error": "이름과 비밀번호를 입력해 주세요."}), 400

    with _accounts_db_lock, _accounts_db() as conn:
        row = conn.execute(
            "SELECT id, role, name, password_hash, level FROM users WHERE role = ? AND name = ?", (role, name)
        ).fetchone()
    if not row or not check_password_hash(row[3], password):
        return jsonify({"error": "이름 또는 비밀번호가 맞지 않아요."}), 401

    session.clear()
    session["user_id"] = row[0]
    session.permanent = True
    return jsonify({"user": _user_public(row)})


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/me")
def auth_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None})
    with _accounts_db_lock, _accounts_db() as conn:
        row = conn.execute("SELECT id, role, name, level FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        session.clear()
        return jsonify({"user": None})
    return jsonify({"user": _user_public(row)})


# 비회원 체험은 익명 쿠키별 누적 2회. 로그인/로그아웃해도 체험 쿠키를 유지한다.
@app.route("/api/practice", methods=["GET", "POST"])
def practice_access():
    token = request.cookies.get("reading_trial")
    if not token or not re.fullmatch(r"[a-f0-9]{64}", token):
        token = secrets.token_hex(32)
    client = hashlib.sha256(token.encode()).hexdigest()
    with _accounts_db_lock, _accounts_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (session.get("user_id"),)).fetchone()
        conn.execute("INSERT OR IGNORE INTO trial_usage (client, used) VALUES (?, 0)", (client,))
        if request.method == "POST" and not user:
            conn.execute("UPDATE trial_usage SET used = used + 1 WHERE client = ? AND used < 2", (client,))
            accepted = conn.execute("SELECT changes()").fetchone()[0] == 1
        else:
            accepted = True
        used = conn.execute("SELECT used FROM trial_usage WHERE client = ?", (client,)).fetchone()[0]
    response = jsonify({"allowed": accepted, "remaining": max(0, 2 - used), "member": bool(user)})
    response.status_code = 200 if accepted else 403
    response.set_cookie("reading_trial", token, max_age=31536000, httponly=True, samesite="Lax", secure=request.is_secure)
    return response


# ---------------- AI 문제 만들기 ----------------


def _today():
    """Gemini 무료 한도와 같은 기준(미국 태평양 시간 자정)으로 날짜를 나눈다."""
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Los_Angeles")
    except Exception:
        tz = timezone(timedelta(hours=-8))
    return datetime.now(tz).strftime("%Y-%m-%d")


def _db():
    USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(USAGE_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS generation_usage ("
        " day TEXT NOT NULL, client TEXT NOT NULL, created_at TEXT NOT NULL, ok INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS generated_sets ("
        " input_hash TEXT PRIMARY KEY, passage_json TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    return conn


def _client_id():
    forwarded = request.headers.get("X-Forwarded-For", "")
    addr = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"
    return hashlib.sha256(addr.encode()).hexdigest()[:16]  # 접속 주소는 해시로만 저장


def _usage(conn, client):
    day = _today()
    total = conn.execute("SELECT COUNT(*) FROM generation_usage WHERE day = ?", (day,)).fetchone()[0]
    mine = conn.execute(
        "SELECT COUNT(*) FROM generation_usage WHERE day = ? AND client = ?", (day, client)
    ).fetchone()[0]
    remaining = max(0, min(limit_per_user() - mine, limit_total() - total))
    return {"remainingToday": remaining, "limitPerUser": limit_per_user(), "usedToday": mine}


# 개인정보로 보이는 값은 외부 AI로 보내지 않는다.
PERSONAL_INFO_PATTERNS = [
    re.compile(r"\d{6}\s*-\s*[1-4]\d{6}"),  # 주민등록번호
    re.compile(r"01[016789][\s-]?\d{3,4}[\s-]?\d{4}"),  # 휴대전화
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),  # 이메일
]


@app.get("/api/generate/status")
def generate_status():
    with _db_lock, _db() as conn:
        usage = _usage(conn, _client_id())
    return jsonify({"enabled": bool(qg.api_key()), "model": qg.model_name(), "questionCount": qg.QUESTION_COUNT, **usage})


@app.post("/api/generate")
def generate():
    level = request.form.get("level", "중학")
    if level not in qg.LEVELS:
        return jsonify({"error": "학교급을 다시 선택해 주세요."}), 400

    upload = request.files.get("file")
    text = None
    pdf_bytes = None
    if upload and upload.filename:
        pdf_bytes = upload.read()
        if not pdf_bytes.startswith(b"%PDF"):
            return jsonify({"error": "PDF 파일만 올릴 수 있어요."}), 400
        if len(pdf_bytes) > MAX_PDF_BYTES:
            return jsonify({"error": "PDF는 5MB 이하만 올릴 수 있어요."}), 400
        source_key = pdf_bytes
    else:
        text = (request.form.get("text") or "").strip()
        if len(text) < MIN_TEXT_CHARS:
            return jsonify({"error": f"지문을 {MIN_TEXT_CHARS}자 이상 넣어 주세요."}), 400
        if len(text) > MAX_TEXT_CHARS:
            return jsonify({"error": f"지문은 {MAX_TEXT_CHARS}자까지 넣을 수 있어요."}), 400
        if any(p.search(text) for p in PERSONAL_INFO_PATTERNS):
            return jsonify({"error": "전화번호·이메일 같은 개인정보는 지우고 다시 넣어 주세요."}), 400
        source_key = text.encode("utf-8")

    input_hash = hashlib.sha256(level.encode() + b"\0" + source_key).hexdigest()
    passage_id = f"ai-{input_hash[:12]}"
    client = _client_id()

    with _db_lock, _db() as conn:
        # 같은 지문·같은 학교급이면 저장해 둔 문제를 다시 쓰고 AI를 호출하지 않는다.
        row = conn.execute(
            "SELECT passage_json FROM generated_sets WHERE input_hash = ?", (input_hash,)
        ).fetchone()
        if row:
            return jsonify({"passage": json.loads(row[0]), "cached": True, **_usage(conn, client)})
        if not qg.api_key():
            return jsonify({"error": "AI 문제 만들기가 아직 설정되지 않았어요."}), 424
        if _usage(conn, client)["remainingToday"] <= 0:
            return jsonify({"error": "오늘 만들 수 있는 횟수를 모두 썼어요. 내일 다시 만들어 주세요.", **_usage(conn, client)}), 429
        # 호출 전에 횟수를 먼저 기록해, 동시에 여러 번 눌러도 한도를 넘지 않게 한다.
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO generation_usage (day, client, created_at, ok) VALUES (?, ?, ?, 0)",
            (_today(), client, now),
        )
        usage_rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    try:
        raw = qg.call_gemini(level, text=text, pdf_bytes=pdf_bytes)
        passage = qg.build_passage(raw, level, passage_id, text=text)
    except qg.GenerationError as err:
        with _db_lock, _db() as conn:
            if err.status in (429, 503):
                # AI가 실제로 일하지 않은 실패(한도 초과·설정 오류)는 횟수에서 빼 준다.
                conn.execute("DELETE FROM generation_usage WHERE rowid = ?", (usage_rowid,))
            usage = _usage(conn, client)
        app.logger.warning("generate failed: %s (%s)", err.message, err.detail)
        # 배포 플랫폼이 5xx 응답 본문을 자체 오류 페이지로 바꿔 버리므로,
        # AI 쪽 실패는 424로 보내 학생에게 안내 문구가 그대로 보이게 한다.
        status = 424 if err.status >= 500 else err.status
        return jsonify({"error": err.message, "detail": err.detail, **usage}), status

    with _db_lock, _db() as conn:
        conn.execute("UPDATE generation_usage SET ok = 1 WHERE rowid = ?", (usage_rowid,))
        conn.execute(
            "INSERT OR REPLACE INTO generated_sets (input_hash, passage_json, model, created_at) VALUES (?, ?, ?, ?)",
            (input_hash, json.dumps(passage, ensure_ascii=False), qg.model_name(), now),
        )
        usage = _usage(conn, client)
    return jsonify({"passage": passage, "cached": False, **usage})


@app.errorhandler(413)
def too_large(_err):
    return jsonify({"error": "PDF는 5MB 이하만 올릴 수 있어요."}), 413


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.get("/")
def index():
    return send_from_directory(ROOT_DIR, "index.html")


# 브라우저에 내려줄 수 있는 폴더. app.py·.env·tests 등 나머지 파일은 절대 서빙하지 않는다.
PUBLIC_DIRS = ("assets", "data")


@app.get("/<path:path>")
def static_files(path):
    """index.html, assets/, data/ 아래 정적 파일만 서빙한다."""
    full_path = (ROOT_DIR / path).resolve()
    if ROOT_DIR not in full_path.parents:
        return jsonify({"error": "not found"}), 404
    parts = full_path.relative_to(ROOT_DIR).parts
    is_public = path == "index.html" or (len(parts) > 1 and parts[0] in PUBLIC_DIRS)
    if not is_public or any(part.startswith(".") for part in parts):
        return jsonify({"error": "not found"}), 404
    if not full_path.is_file():
        return jsonify({"error": "not found"}), 404
    return send_from_directory(ROOT_DIR, path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
