"""
Bark 推送封装。
Bark 是 iOS 上的一个开源推送 App：https://github.com/Finb/Bark
在 App 里能拿到一个形如 https://api.day.app/xxxxxxxx 的专属 Key，
这里只需要传 Key（xxxxxxxx 那一段），不需要传完整 URL。
"""
import requests


def send_bark(key: str, title: str, body: str, icon_url: str | None = None,
               group: str = "心跳", url: str | None = None, timeout: int = 10):
    """发送一条 Bark 推送。返回 (是否成功, 详情)。"""
    if not key:
        return False, "未配置 BARK_KEY"

    payload = {
        "device_key": key,
        "title": title,
        "body": body,
        "group": group,
    }
    if icon_url:
        payload["icon"] = icon_url
    if url:
        payload["url"] = url

    try:
        r = requests.post("https://api.day.app/push", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("code") == 200:
            return True, data
        return False, data
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    # 简单自测：python bark.py <你的BarkKey>
    import sys
    if len(sys.argv) < 2:
        print("用法: python bark.py <BarkKey>")
    else:
        ok, info = send_bark(sys.argv[1], "测试推送", "如果你收到了这条，说明 Bark 配置没问题 🎉")
        print("成功" if ok else "失败", info)
