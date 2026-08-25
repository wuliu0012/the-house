"""
toy_bridge.py — SVAKOM 相姬 Alberta 本地 WebSocket 桥接
网页(claude-chat-v13.html) <--WebSocket--> 本脚本 <--bleak/BLE--> 玩具

依赖：pip install bleak websockets

使用：
  1. 先用 scan_toy.py 找到玩具蓝牙地址
  2. 把下面 DEVICE_ADDRESS 改成找到的地址
  3. python toy_bridge.py
  4. 打开网页 → 玩具设置 → 连接本地桥接（默认 ws://127.0.0.1:8765）

BLE 协议（来自 PPT 逆向工程）：
  服务:  0000ffe0-0000-1000-8000-00805f9b34fb
  特征:  0000ffe1-0000-1000-8000-00805f9b34fb
  吮吸(0x09): 55 09 00 00 [模式1-5] [强度1-3] 00，停止: 55 09 00 00 00 00 00
  振动(0x03): 55 03 00 00 01 [强度1-10] 00，停止: 55 03 00 00 00 00 00

  ⚠️ 注意：第6字节（强度1-3）目前是按说明书文字描述猜测的位置，
  之前版本这里一直硬编码成 0x01，从未实际验证过不同强度对应的字节。
  拿到玩具后请用 test_suck_strength.py 实测，确认有效后再放心用。

网页发来的 JSON：
  {"cmd":"suck","mode":1-5,"strength":1-3}   # strength 省略时默认 1
  {"cmd":"vibe","level":1-10}
  {"cmd":"stop"}
"""

import asyncio, json, logging
from bleak import BleakClient
import websockets

# ===== 改成你的玩具蓝牙地址 =====
DEVICE_ADDRESS = "XX:XX:XX:XX:XX:XX"
# ==================================

FFE1      = "0000ffe1-0000-1000-8000-00805f9b34fb"
WS_HOST   = "0.0.0.0"   # 监听所有网卡，不绑死某个IP；手机连的地址去用 ipconfig 查电脑当前真实IP
WS_PORT   = 8765

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("toy_bridge")


def _suck(mode: int, strength: int = 1) -> bytes:
    m = max(0, min(5, mode))
    # 实测映射：弱=0x04, 中=0x08, 强=0x0A（最大有效值）
    _smap = {1: 0x04, 2: 0x08, 3: 0x0A}
    s = _smap.get(max(1, min(3, strength)), 0x04) if m > 0 else 0x00
    return bytes([0x55, 0x09, 0x00, 0x00, m, s, 0x00])

def _vibe(level: int) -> bytes:
    l = max(0, min(10, level))
    return bytes([0x55, 0x03, 0x00, 0x00, 0x01 if l > 0 else 0x00, l, 0x00])


class ToyBridge:
    def __init__(self, address: str):
        self.address = address
        self.client: BleakClient | None = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> bool:
        if self.client and self.client.is_connected:
            return True
        try:
            log.info("连接玩具 %s ...", self.address)
            self.client = BleakClient(self.address)
            await self.client.connect()
            log.info("玩具已连接 ✓")
            return True
        except Exception as e:
            log.warning("连接失败: %s", e)
            self.client = None
            return False

    async def write(self, data: bytes) -> bool:
        async with self._lock:
            if not await self._connect():
                return False
            try:
                await self.client.write_gatt_char(FFE1, data)
                return True
            except Exception as e:
                log.warning("写入失败: %s", e)
                self.client = None
                return False

    async def dispatch(self, msg: dict):
        cmd = msg.get("cmd")
        if cmd == "suck":
            await self.write(_suck(int(msg.get("mode", 0)), int(msg.get("strength", 1))))
        elif cmd == "vibe":
            await self.write(_vibe(int(msg.get("level", 0))))
        elif cmd == "stop":
            await self.write(_suck(0))
            await asyncio.sleep(0.05)
            await self.write(_vibe(0))
        else:
            log.warning("未知指令: %s", msg)


bridge = ToyBridge(DEVICE_ADDRESS)


async def ws_handler(websocket):
    log.info("网页已接入")
    ok = await bridge._connect()
    await websocket.send(json.dumps(
        {"status": "connected", "device": bridge.address} if ok
        else {"status": "error", "message": "无法连接玩具，请检查地址/开机状态"}
    ))
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await bridge.dispatch(msg)
    except websockets.exceptions.ConnectionClosed:
        pass
    log.info("网页已断开")


async def main():
    log.info("就绪！WebSocket 服务：ws://%s:%s", WS_HOST, WS_PORT)
    async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
