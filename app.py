"""읽는 힘 — 비문학 독해 연습: Flask 백엔드.

정적 파일(index.html, assets/)과 지문 데이터(data/passages.json)를 서버에서 제공한다.
외부 API를 호출해야 할 때는 API 키 등 민감한 값을 브라우저에 노출하지 않도록
이 서버(백엔드)에서 호출하고 결과만 클라이언트로 내려준다.

로컬 실행:
    pip install -r requirements.txt
    python3 app.py
    브라우저에서 http://localhost:8000 접속

배포 시에는 플랫폼이 PORT 환경변수를 주입하며, 이 앱은 0.0.0.0에 바인딩한다.
"""

import json
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

ROOT_DIR = Path(__file__).resolve().parent
DATA_PATH = ROOT_DIR / "data" / "passages.json"

app = Flask(__name__, static_folder=None)

# 외부 API를 연동할 때 쓸 설정값. 실제 키는 코드에 하드코딩하지 않고
# 배포 환경변수(EXTERNAL_API_KEY, EXTERNAL_API_BASE_URL)로 주입한다.
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")
EXTERNAL_API_BASE_URL = os.environ.get("EXTERNAL_API_BASE_URL", "")


def load_passages():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/passages")
def api_passages():
    """지문·문제 데이터를 서버에서 읽어 내려준다.

    지금은 로컬 JSON 파일을 반환하지만, 추후 외부 API에서 지문을 가져오도록
    바꾸더라도 프런트엔드(assets/js/app.js)는 이 엔드포인트만 바라보므로
    수정이 필요 없다.
    """
    try:
        passages = load_passages()
    except (OSError, json.JSONDecodeError):
        app.logger.exception("failed to load passages")
        return jsonify({"error": "failed to load passages"}), 500
    return jsonify(passages)


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
