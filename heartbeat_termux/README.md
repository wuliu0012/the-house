# 心跳唤醒装置（Termux + Python 版）

参考了 dylan-heartbeat 的思路，但**不做网关/代理**：你的自建前端（`claude-chat-heartbeat.html`）
该怎么直接连 API 还怎么连，跟这套心跳系统完全解耦。心跳脚本只是"另外一个人"，
拿着同一份 API 配置，隔一段时间自己看看聊天记录、自己决定要不要主动说句话、
决定说了就通过 Bark 推到你手机上，同时把这句话"写"回你前端的聊天记录里。

## 整体架构

```
手机浏览器打开 claude-chat-heartbeat.html（你平时聊天用这个，完全不受影响）
        │
        │ 每次保存对话 → POST /sync（防抖3秒）      每30秒 → GET /pull 看看有没有新消息
        │ 每次发消息   → POST /touch（刷新"最后互动时间"）
        ▼
Termux 上跑 server.py（Flask，只负责存文件，不碰 AI）
        │
        │ 落盘到 data/*.json
        ▼
Termux 上跑 heartbeat.py（定时检查）
        │
        │ 空闲够久 → 直接用你在前端填的 baseUrl+apiKey+model 调用 AI
        │ AI 决定要不要说话，要说 → 存进 pending_push.json，等前端来拉
        ▼
      Bark 推送到你手机
```

**关键点**：`heartbeat.py` 是直接拿你在前端"设置"里填的 API Key 自己调 API 的，
和 dylan-heartbeat 的 `server.js` 网关模式不一样——这里没有任何东西站在你和 AI 的
正常对话中间转发，心跳只是一个独立的、偶尔插一句话的"旁路"。

## 文件说明

| 文件 | 作用 |
|---|---|
| `server.py` | Flask 服务器，负责接前端同步 / 提供拉取接口，纯文件存储，不调用AI |
| `heartbeat.py` | 真正的心跳逻辑：判断要不要醒、调AI生成内容、发Bark |
| `bark.py` | Bark 推送的小封装 |
| `.env.example` | 配置模板 |
| `data/` | 运行时自动生成，存对话历史、状态、待推送队列（全是本地JSON文件） |

## 安装（Termux）

```bash
pkg install python -y   # 如果还没装
cd ~
# 把这个 heartbeat_termux 文件夹传到手机上（比如用 git clone 你自己fork的仓库，
# 或者用 Termux 的 termux-storage 从下载目录 cp 过来）
cd heartbeat_termux
pip install -r requirements.txt
cp .env.example .env
nano .env   # 至少填一下 BARK_KEY，其他默认值可以先不动
```

## 启动

**两个东西要分开起，各占一个终端 / session：**

```bash
# 终端1：同步服务器（一直得开着，前端要连它）
python server.py
# 看到 "✅ 心跳同步服务器运行在 http://0.0.0.0:5000" 就对了

# 终端2：心跳脚本（常驻模式，自己管理白天/夜间检查间隔）
python heartbeat.py
```

想让它们在 Termux 关掉/锁屏后继续跑，装 `termux-services` 或者简单点用 `nohup`：

```bash
nohup python server.py > server.log 2>&1 &
nohup python heartbeat.py > heartbeat.log 2>&1 &
```

也可以不用常驻模式，改用 crontab 定时跑单次检查（更省电，Termux上要装 `termux-services` + `cronie`）：
```bash
# 每10分钟跑一次
*/10 * * * * cd ~/heartbeat_termux && python heartbeat.py --once >> heartbeat.log 2>&1
```

## 配置前端

1. 用手机连到 Termux 服务器所在的 IP（同一个 WiFi 下 `192.168.x.x:5000`，
   Termux 里跑 `ifconfig` 或 `ip addr` 能看到自己的局域网 IP）
2. 打开 `claude-chat-heartbeat.html`，进「设置 → API」，最下面多了一栏
   **"心跳同步地址"**，填 `http://192.168.x.x:5000`
3. 保存。之后正常聊天，心跳脚本就会在后台默默观察，够久没互动就自己找个理由跟你说句话。

## 调参

都在 `.env` 里：

- `DAY_START_HOUR` / `NIGHT_START_HOUR`：怎么划分白天夜间
- `DAY_INTERVAL_MIN` / `NIGHT_INTERVAL_MIN`：空闲多久才允许唤醒一次（默认60/120分钟，跟原项目一致）
- `CHECK_INTERVAL_DAY_SEC` / `CHECK_INTERVAL_NIGHT_SEC`：常驻模式下多久检查一次要不要唤醒
- `CONTEXT_MAX_MESSAGES`：心跳判断时给AI看最近几条历史（太多会费token）

## 已知的简化点（可以之后自己再改）

- `history.json` 里目前不存精确时间戳，`last_user_ts` 是靠前端主动调 `/touch` 更新的
  （在 `sendMessage()` 里发消息那一刻打点），不是每条历史消息都有独立时间——够用，但
  如果你想要更精细的"什么时候说的哪句话"，可以在前端 push 历史条目时顺手加个 `ts` 字段，
  `/sync` 里已经预留了读取 `ts` 的空间。
- 多窗口场景下心跳只会同步 "当前打开的那个窗口"（`activeWin()`），如果你有多个对话窗口，
  心跳只关心你正在看的这个。
- Bark 推送内容目前直接截断到200字，超长的话会被截断，可以自己在 `heartbeat.py` 的
  `send_bark(...)` 那行调整。

## 测试

```bash
python bark.py <你的BarkKey>      # 单独测试Bark推送通不通
python heartbeat.py --once        # 手动跑一次心跳检查（看日志输出）
curl http://localhost:5000/status # 看当前状态（对话条数、上次互动时间等）
```
