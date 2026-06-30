"""
scan_toy.py — 用开关机对比法找到玩具蓝牙地址（PPT 第5页方法）

步骤：
  1. 玩具开机 → python scan_toy.py  → 记录全部设备
  2. 玩具关机 → python scan_toy.py  → 再记录一次
  3. 对比两次，关机后消失的就是你的玩具，记下地址（XX:XX:XX:XX:XX:XX）
  4. 填入 toy_bridge.py 的 DEVICE_ADDRESS
"""

import asyncio
from bleak import BleakScanner


async def scan():
    print("扫描中，15秒……")
    devices = await BleakScanner.discover(timeout=15)
    if not devices:
        print("没有找到任何蓝牙设备，请确认蓝牙已开启。")
        return
    print(f"共发现 {len(devices)} 个设备：")
    for d in sorted(devices, key=lambda x: x.name or ""):
        print(f"  {d.name or '(无名称)':<30} | {d.address}")


if __name__ == "__main__":
    asyncio.run(scan())
