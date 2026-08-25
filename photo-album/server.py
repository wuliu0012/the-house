"""
相册存储服务（Flask，零额外依赖）。

职责很简单：
1. 管理相册（新建 / 删除 / 列表）
2. 存取照片（base64 jpeg 落盘到 photos/ 目录）
3. 照片描述的增改

只监听 127.0.0.1:8086，公网访问走 nginx 反代 /photo-api/。
鉴权：请求头 X-Album-Token 必须匹配 .env 里的 ALBUM_TOKEN。
"""
import base64
import json
import os
import re
import threading
import time
import uuid

from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PHOTO_DIR = os.path.join(DATA_DIR, "photos")
ALBUMS_FILE = os.path.join(DATA_DIR, "albums.json")
os.makedirs(PHOTO_DIR, exist_ok=True)

# token 从同目录 .env 读（KEY=TOKEN 格式），避免写死在代码里
TOKEN = ""
ELEVENLABS_KEY = ""   # 默认 TTS 凭据（前端可在请求里覆盖）
ELEVENLABS_VOICE = ""  # 默认音色 ID
_env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("ALBUM_TOKEN="):
                TOKEN = line.split("=", 1)[1].strip()
            elif line.startswith("ELEVENLABS_KEY="):
                ELEVENLABS_KEY = line.split("=", 1)[1].strip()
            elif line.startswith("ELEVENLABS_VOICE="):
                ELEVENLABS_VOICE = line.split("=", 1)[1].strip()

TTS_CACHE_DIR = os.path.join(DATA_DIR, "tts_cache")
os.makedirs(TTS_CACHE_DIR, exist_ok=True)

lock = threading.Lock()

app = Flask(__name__)


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Album-Token"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    return resp


def _load_albums():
    if not os.path.exists(ALBUMS_FILE):
        return []
    try:
        with open(ALBUMS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_albums(albums):
    tmp = ALBUMS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(albums, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ALBUMS_FILE)


def _auth():
    return TOKEN and request.headers.get("X-Album-Token", "") == TOKEN


def _photo_path(pid):
    # 只允许安全字符，防目录穿越；实际后缀按存盘时的 ext 从 albums.json 里查
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", pid or ""):
        return None
    # 先按记录里的 file 名找（jpeg/png/webp），再兜底旧 .jpg
    for albums in (_load_albums(),):
        for a in albums:
            for p in a.get("photos", []):
                if p["id"] == pid and p.get("file"):
                    return os.path.join(PHOTO_DIR, p["file"])
    return os.path.join(PHOTO_DIR, pid + ".jpg")


def _album_of(albums, aid):
    for a in albums:
        if a["id"] == aid:
            return a
    return None


def _count(album):
    return len(album.get("photos", []))


@app.route("/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return "", 204


@app.before_request
def check_auth():
    # 静态健康检查放行
    if request.path == "/health":
        return None
    if not _auth():
        return jsonify(error="unauthorized"), 401
    return None


@app.route("/health")
def health():
    return jsonify(ok=True)


# ── 相册 ──

@app.route("/albums", methods=["GET"])
def list_albums():
    albums = _load_albums()
    return jsonify([{"id": a["id"], "name": a["name"], "count": _count(a)} for a in albums])


@app.route("/albums", methods=["POST"])
def create_album():
    name = (request.json or {}).get("name", "").strip()[:30]
    if not name:
        return jsonify(error="相册名不能为空"), 400
    with lock:
        albums = _load_albums()
        if any(a["name"] == name for a in albums):
            return jsonify(error="同名相册已存在"), 400
        album = {"id": uuid.uuid4().hex[:12], "name": name, "created": int(time.time()), "photos": []}
        albums.append(album)
        _save_albums(albums)
        return jsonify({"id": album["id"], "name": album["name"], "count": 0}), 201


@app.route("/albums/<aid>", methods=["DELETE"])
def delete_album(aid):
    with lock:
        albums = _load_albums()
        album = _album_of(albums, aid)
        if not album:
            return jsonify(error="相册不存在"), 404
        for p in album.get("photos", []):
            path = _photo_path(p["id"])
            if path and os.path.exists(path):
                os.remove(path)
        albums = [a for a in albums if a["id"] != aid]
        _save_albums(albums)
    return jsonify(ok=True)


# ── 照片 ──

@app.route("/albums/<aid>/photos", methods=["GET"])
def list_photos(aid):
    album = _album_of(_load_albums(), aid)
    if not album:
        return jsonify(error="相册不存在"), 404
    out = []
    for p in album.get("photos", []):
        path = _photo_path(p["id"])
        size = os.path.getsize(path) if path and os.path.exists(path) else 0
        out.append({"id": p["id"], "desc": p.get("desc", ""), "t": p.get("t", 0), "size": size})
    return jsonify(out)


@app.route("/photos", methods=["POST"])
def save_photo():
    body = request.json or {}
    data_url = body.get("dataUrl", "")
    desc = (body.get("desc") or "").strip()[:50]
    m = re.fullmatch(r"data:image/(jpeg|png|webp);base64,(.+)", data_url, re.S)
    if not m:
        return jsonify(error="dataUrl 必须是 base64 图片"), 400
    ext = m.group(1)
    raw = base64.b64decode(m.group(2))
    if len(raw) > 8 * 1024 * 1024:
        return jsonify(error="图片超过 8MB 上限"), 400
    with lock:
        albums = _load_albums()
        album = _album_of(albums, body.get("albumId"))
        if not album:
            return jsonify(error="相册不存在"), 404
        pid = uuid.uuid4().hex[:16]
        fname = pid + "." + ext
        with open(os.path.join(PHOTO_DIR, fname), "wb") as f:
            f.write(raw)
        entry = {"id": pid, "file": fname, "desc": desc, "t": int(time.time())}
        album.setdefault("photos", []).append(entry)
        _save_albums(albums)
        return jsonify({"id": pid, "desc": desc, "t": entry["t"]}), 201


@app.route("/photo/<pid>", methods=["GET"])
def get_photo(pid):
    path = _photo_path(pid)
    if not path or not os.path.exists(path):
        return jsonify(error="照片不存在"), 404
    with open(path, "rb") as f:
        raw = f.read()
    mime = "image/png" if path.endswith(".png") else ("image/webp" if path.endswith(".webp") else "image/jpeg")
    return jsonify({"id": pid, "dataUrl": f"data:{mime};base64," + base64.b64encode(raw).decode()})


@app.route("/photo/<pid>", methods=["DELETE"])
def delete_photo(pid):
    with lock:
        albums = _load_albums()
        found = False
        for a in albums:
            before = len(a.get("photos", []))
            a["photos"] = [p for p in a.get("photos", []) if p["id"] != pid]
            if len(a["photos"]) != before:
                found = True
                break
        if not found:
            return jsonify(error="照片不存在"), 404
        _save_albums(albums)
    path = _photo_path(pid)
    if path and os.path.exists(path):
        os.remove(path)
    return jsonify(ok=True)


@app.route("/photo/<pid>/desc", methods=["POST"])
def set_desc(pid):
    desc = ((request.json or {}).get("desc") or "").strip()[:50]
    with lock:
        albums = _load_albums()
        for a in albums:
            for p in a.get("photos", []):
                if p["id"] == pid:
                    p["desc"] = desc
                    _save_albums(albums)
                    return jsonify(ok=True, desc=desc)
    return jsonify(error="照片不存在"), 404


# ── TTS（ElevenLabs 代理 + 磁盘缓存）──
# 前端传 {text, apiKey?, voiceId?}；apiKey/voiceId 缺省时用 .env 的默认值。
# 同一段 (text, voice, key) 只生成一次，之后直接回缓存文件。

@app.route("/tts", methods=["POST"])
def tts():
    import hashlib
    body = request.json or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify(error="text 不能为空"), 400
    if len(text) > 500:
        return jsonify(error="文字超过 500 字上限"), 400
    key = (body.get("apiKey") or ELEVENLABS_KEY).strip()
    voice = (body.get("voiceId") or ELEVENLABS_VOICE).strip()
    if not key or not voice:
        return jsonify(error="未配置 ElevenLabs 凭据"), 400
    h = hashlib.sha1(f"{text}|{voice}|{key}".encode("utf-8")).hexdigest()
    cache_path = os.path.join(TTS_CACHE_DIR, h + ".mp3")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return jsonify(url="/tts_file/" + h + ".mp3", cached=True)
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode("utf-8"),
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio = resp.read()
        if not audio[:3] in (b"ID3", b"\xff\xfb"):
            return jsonify(error="ElevenLabs 返回的不是音频"), 502
        tmp = cache_path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(audio)
        os.replace(tmp, cache_path)
        return jsonify(url="/tts_file/" + h + ".mp3", cached=False)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("detail", {}).get("message", "")
        except Exception:
            pass
        status = 401 if e.code == 401 else 502
        return jsonify(error=f"ElevenLabs 错误 HTTP {e.code}{(': ' + detail) if detail else ''}（检查 key/音色 ID/配额）"), status
    except Exception as e:
        return jsonify(error="生成失败: " + str(e)), 502


@app.route("/tts_file/<fname>")
def tts_file(fname):
    # 文件名只允许 hash.mp3 形态，防目录穿越
    import re
    if not re.fullmatch(r"[A-Za-z0-9_\-]+\.mp3", fname):
        return jsonify(error="bad filename"), 400
    path = os.path.join(TTS_CACHE_DIR, fname)
    if not os.path.exists(path):
        return jsonify(error="音频不存在"), 404
    with open(path, "rb") as f:
        raw = f.read()
    resp = app.response_class(raw, mimetype="audio/mpeg")
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8086, threaded=True)
