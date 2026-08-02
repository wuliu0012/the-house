#!/usr/bin/env python3
"""
心跳唤醒脚本。

跟前端完全解耦：只读 server.py 落盘的 data/*.json，
自己直接拿 (baseUrl + apiKey + model) 调用 AI（跟前端用的是同一个 API，
不经过任何网关/代理），判断要不要主动说话，要说的话就发 Bark 推送。

用法：
  常驻模式（自己管理间隔，适合 nohup / tmux / termux-services 常驻跑）：
    python heartbeat.py

  单次模式（自己只检查一次就退出，适合配合 crontab 定时跑）：
    python heartbeat.py --once
"""
import argparse
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from bark import send_bark

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
CFG_FILE = os.path.join(DATA_DIR, "cfg.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending_push.json")
EXTRA_FILE = os.path.join(DATA_DIR, "heartbeat_extra.json")

# ── 配置（.env 里改） ──
TIMEZONE = os.environ.get("HEARTBEAT_TZ", "Asia/Shanghai")
BARK_KEY = os.environ.get("BARK_KEY", "")
BARK_ICON = os.environ.get("BARK_ICON", "")
DAY_START_HOUR = int(os.environ.get("DAY_START_HOUR", "10"))     # 白天从几点开始
NIGHT_START_HOUR = int(os.environ.get("NIGHT_START_HOUR", "0"))  # 夜间从几点开始（0点）
DAY_INTERVAL_MIN = int(os.environ.get("DAY_INTERVAL_MIN", "60"))     # 白天：空闲多久后可以唤醒
NIGHT_INTERVAL_MIN = int(os.environ.get("NIGHT_INTERVAL_MIN", "120"))  # 夜间：空闲多久后可以唤醒
CHECK_INTERVAL_DAY_SEC = int(os.environ.get("CHECK_INTERVAL_DAY_SEC", "600"))     # 常驻模式：白天多久检查一次
CHECK_INTERVAL_NIGHT_SEC = int(os.environ.get("CHECK_INTERVAL_NIGHT_SEC", "7200"))  # 常驻模式：夜间多久检查一次
CONTEXT_MAX_MESSAGES = int(os.environ.get("CONTEXT_MAX_MESSAGES", "40"))  # 给AI看最近多少条历史

SILENCE_MARK = "<SILENCE/>"


def load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def now_ms():
    return int(time.time() * 1000)


def is_daytime():
    hour = datetime.now(ZoneInfo(TIMEZONE)).hour
    if DAY_START_HOUR <= NIGHT_START_HOUR:
        return DAY_START_HOUR <= hour < NIGHT_START_HOUR
    # 跨零点的情况（比如白天10点~夜间0点）
    return hour >= DAY_START_HOUR or hour < NIGHT_START_HOUR


def build_messages(sys_prompt, history, extra):
    heartbeat_instruction = (
        "\n\n---\n"
        "[心跳系统提示]：这是一次自动触发的心跳检查，不是对方发来的消息，对方现在看不到这段提示。\n"
        "如果你觉得此刻适合主动联系对方（比如很久没聊、想起点什么、单纯想打个招呼、想分享点什么），"
        "请直接输出你想说的这段话本身（会通过 Bark 推送到对方手机上，所以不要太长，一两句话就好）。\n"
        f"如果现在不合适主动开口，就只输出 {SILENCE_MARK}，不要输出任何其他文字，也不要解释原因。"
    )
    full_sys = (sys_prompt or "") + heartbeat_instruction

    combined = list(history)
    existing = {(h.get("role"), h.get("content")) for h in history}
    for e in extra:
        if (e.get("role"), e.get("content")) not in existing:
            combined.append(e)

    msgs = []
    for entry in combined[-CONTEXT_MAX_MESSAGES:]:
        role = entry.get("role")
        content = entry.get("content")
        if not isinstance(content, str) or not content:
            continue
        if role == "user":
            msgs.append({"role": "user", "content": content})
        elif role == "ai":
            msgs.append({"role": "assistant", "content": content})
    # 心跳自检触发消息（不会真的展示给用户，只是给AI一个"该你判断了"的信号）
    msgs.append({"role": "user", "content": "（心跳自检触发，请按系统提示判断此刻是否要主动说话）"})
    return full_sys, msgs


def call_ai(cfg, sys_prompt, msgs):
    base = (cfg.get("baseUrl") or "https://api.anthropic.com").rstrip("/")
    api_type = cfg.get("apiType", "anthropic")
    model = cfg.get("model") or "claude-opus-4-6"
    api_key = cfg.get("apiKey", "")
    if not api_key:
        raise RuntimeError("cfg.json 里没有 apiKey —— 先在前端「设置」里保存一次配置，让它同步过来")

    if api_type == "openai":
        url = f"{base}/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        body = {
            "model": model,
            "max_tokens": 300,
            "messages": [{"role": "system", "content": sys_prompt}] + msgs,
        }
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    else:
        url = f"{base}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {"model": model, "max_tokens": 300, "system": sys_prompt, "messages": msgs}
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def tick():
    cfg = load(CFG_FILE, {})
    history = load(HISTORY_FILE, [])
    extra = load(EXTRA_FILE, [])
    state = load(STATE_FILE, {})

    if not cfg.get("apiKey"):
        print("[心跳] 还没收到过前端同步的配置，跳过本次检查（先在前端保存一次设置）")
        return

    last_user_ts = state.get("last_user_ts", 0)
    last_heartbeat_ts = state.get("last_heartbeat_ts", 0)
    last_active_ts = max(last_user_ts, last_heartbeat_ts)
    idle_min = (now_ms() - last_active_ts) / 60000 if last_active_ts else 10 ** 9

    daytime = is_daytime()
    threshold = DAY_INTERVAL_MIN if daytime else NIGHT_INTERVAL_MIN

    print(f"[心跳] 距上次互动约 {idle_min:.1f} 分钟，阈值 {threshold} 分钟（当前判定为{'白天' if daytime else '夜间'}）")
    if idle_min < threshold:
        return

    sys_prompt, msgs = build_messages(cfg.get("sysPrompt", ""), history, extra)
    try:
        text = call_ai(cfg, sys_prompt, msgs)
    except Exception as e:
        print(f"[心跳] 调用 AI 失败：{e}")
        return

    state["last_heartbeat_ts"] = now_ms()
    save(STATE_FILE, state)

    if not text or SILENCE_MARK in text:
        print("[心跳] AI 判断现在不适合主动说话，本次不推送")
        return

    print(f"[心跳] 生成主动消息：{text[:60]}{'...' if len(text) > 60 else ''}")

    entry = {"role": "ai", "content": text, "heartbeat": True}
    extra.append(entry)
    save(EXTRA_FILE, extra)

    pending = load(PENDING_FILE, [])
    pending.append(entry)
    save(PENDING_FILE, pending)

    if BARK_KEY:
        ok, info = send_bark(BARK_KEY, "💭", text[:200], icon_url=BARK_ICON or None)
        print(f"[心跳] Bark 推送{'成功' if ok else '失败：' + str(info)}")
    else:
        print("[心跳] 未配置 BARK_KEY，跳过手机推送（消息已经写入待拉取队列，前端下次轮询时仍会显示出来）")


def main():
    parser = argparse.ArgumentParser(description="心跳唤醒脚本")
    parser.add_argument("--once", action="store_true", help="只检查一次就退出（配合 crontab 用）")
    args = parser.parse_args()

    if args.once:
        tick()
        return

    print("[心跳] 常驻模式启动，Ctrl+C 退出")
    while True:
        try:
            tick()
        except Exception as e:
            print(f"[心跳] 本轮检查出错：{e}")
        sleep_sec = CHECK_INTERVAL_DAY_SEC if is_daytime() else CHECK_INTERVAL_NIGHT_SEC
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()
