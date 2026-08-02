"""
心跳同步服务器（Flask）。

跑在你自己的 Termux 服务器上，职责很简单，只做三件事：
1. POST /sync   —— 前端每次保存对话时把 (配置 + 完整对话历史) 同步过来，
                    存成本地文件，作为 heartbeat.py 判断"该不该主动说话"的上下文。
2. POST /touch  —— 前端每次用户发送消息时调用一下，刷新"最后互动时间"。
3. GET  /pull   —— 前端定期轮询，取走 heartbeat.py 生成、还没被前端看到的主动消息。
4. GET  /status —— 方便你自己在浏览器里看一眼当前状态（调试用）。

不做转发、不代理你和 AI 的正常对话 —— 那部分前端仍然直接连 API，跟 heartbeat 完全解耦。
"""
import json
import os
import threading
import time

from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")       # 前端同步过来的完整对话（前端说了算）
CFG_FILE = os.path.join(DATA_DIR, "cfg.json")                # baseUrl/apiKey/apiType/model/sysPrompt
STATE_FILE = os.path.join(DATA_DIR, "state.json")            # last_user_ts / last_heartbeat_ts
PENDING_FILE = os.path.join(DATA_DIR, "pending_push.json")   # 待前端拉取的心跳消息
EXTRA_FILE = os.path.join(DATA_DIR, "heartbeat_extra.json")  # 心跳生成、前端还没确认收到的消息（供heartbeat自己接着用作上下文）

lock = threading.Lock()

app = Flask(__name__)


# 简单手写 CORS，避免依赖 flask-cors（Termux 上少装一个包）
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.route("/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return "", 204


def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def now_ms():
    return int(time.time() * 1000)


@app.route("/sync", methods=["POST"])
def sync():
    body = request.get_json(force=True, silent=True) or {}
    cfg = body.get("cfg", {})
    history = body.get("history", [])

    with lock:
        _save(CFG_FILE, cfg)
        _save(HISTORY_FILE, history)

        # 清理掉已经出现在前端最新历史里的心跳消息，避免 heartbeat 上下文里重复
        synced_texts = {(h.get("role"), h.get("content")) for h in history}
        extra = _load(EXTRA_FILE, [])
        extra = [e for e in extra if (e.get("role"), e.get("content")) not in synced_texts]
        _save(EXTRA_FILE, extra)

    return jsonify({"ok": True, "history_len": len(history)})


@app.route("/touch", methods=["POST"])
def touch():
    with lock:
        state = _load(STATE_FILE, {})
        state["last_user_ts"] = now_ms()
        _save(STATE_FILE, state)
    return jsonify({"ok": True})


@app.route("/pull", methods=["GET"])
def pull():
    with lock:
        pending = _load(PENDING_FILE, [])
        _save(PENDING_FILE, [])
    return jsonify({"entries": pending})


@app.route("/status", methods=["GET"])
def status():
    with lock:
        state = _load(STATE_FILE, {})
        pending = _load(PENDING_FILE, [])
        history = _load(HISTORY_FILE, [])
        cfg = _load(CFG_FILE, {})
    safe_cfg = {**cfg, "apiKey": ("已设置" if cfg.get("apiKey") else "未设置")}
    return jsonify({
        "state": state,
        "pending_count": len(pending),
        "history_len": len(history),
        "cfg": safe_cfg,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"✅ 心跳同步服务器运行在 http://0.0.0.0:{port}")
    print("   前端「设置 → 心跳同步地址」填这个地址（用手机能访问到的那个 IP）")
    app.run(host="0.0.0.0", port=port)
