# Claude Chat v16 使用说明

## 这是什么

一个 AI 对话前端，单个 HTML 文件，双击打开即可在本地使用，也可以部署到服务器供多人访问。支持 Claude（Anthropic）和任何 OpenAI 兼容接口，可选接入蓝牙玩具控制。

请求直接从你的浏览器发到 AI 服务商，**不经过任何第三方服务器**。

---

## 快速开始

1. 双击打开 `claude-chat-v16_2_2.html`
2. 点击右上角 **设置（⚙）**
3. 在 **API** 标签页填入你的 API Key
4. 选好模型，保存，开始对话

> 本地直接使用无需任何服务器，所有数据保存在本机浏览器中。

---

## 设置说明

### API 标签页

| 项目 | 说明 |
|------|------|
| API Key | 你的 Anthropic 或 OpenAI 兼容 API Key |
| Base URL | 默认 `https://api.anthropic.com`，使用中转或其他服务时修改 |
| API 类型 | Anthropic（Claude）或 OpenAI 兼容 |
| 模型 | 填写模型名称，或点"获取列表"自动拉取 |
| 最大 Token | 单次回复最大长度 |
| Temperature / Top P | 控制回复随机性，默认值适合大多数场景 |
| 上下文条数 | 每次发送携带的历史消息数，0 = 不限 |
| 系统提示词 | 设定 AI 角色或行为规则 |

### MCP 标签页

填入 MCP 服务地址可为 AI 接入外部工具（如搜索、文件操作等）。每行一个 URL，保存后自动连接。

---

## 主要功能

### 多窗口对话
左侧边栏可新建、切换、重命名对话窗口，各窗口历史独立保存。

### 持久记忆
AI 可以在对话中主动更新"记忆"，下次对话时自动带入。记忆内容可在设置中查看和手动编辑。顶栏显示"🧠 记忆已启用"时表示有记忆内容生效。

### 图片输入
可粘贴图片（Ctrl+V）或点击附件按钮上传，发送给支持视觉的模型。

### 发送与换行
- **Enter**：发送消息
- **Shift + Enter**：换行

### 导出聊天记录
点击顶栏右侧的 **↑ 导出** 按钮，可将当前对话窗口的聊天记录导出为：
- **Markdown (.md)**：格式整洁，适合阅读和分享
- **JSON (.json)**：包含完整结构数据，适合程序处理

导出内容仅包含文字消息，图片不随历史持久化。

### 调试工具
点击顶栏右侧的 **🔍 调试** 按钮可开启调试模式。开启后，下次发送含图片的消息时会弹窗显示实际发送给 API 的内容（图片数量、base64 片段、文字内容），方便排查图片识别异常或请求格式问题。再次点击关闭。

### MCP 工具调用结果
AI 调用 MCP 工具时，对话中会出现一个可折叠的工具块，点击展开后可以看到：
- **调用参数**：AI 传给工具的具体入参（JSON 格式）
- **返回结果**：工具实际返回给 AI 的原始内容

方便确认工具是否正常执行、返回了什么数据。

### 环境感知
启用定位权限后，AI 会自动获知当前时间、天气、位置，顶栏会显示当前天气状态。

---

## 玩具控制（可选）

需要配合 `toy_bridge.py` 本地桥接脚本使用，适用于 SVAKOM Alberta。

### 启动桥接

```bash
pip install bleak websockets
python toy_bridge.py
```

运行前先用文本编辑器打开 `toy_bridge.py`，将 `DEVICE_ADDRESS` 改为你的玩具蓝牙地址（用 `scan_toy.py` 扫描获取）。

脚本启动后默认监听 `ws://127.0.0.1:8765`。

### 连接玩具

设置面板 → 玩具标签页 → 填入桥接地址 → 点击连接。

### 手动控制

| 按钮 | 说明 |
|------|------|
| 阵雷 / 雨点 / 鼓点 / 水滴 | 吮吸模式 1-4，各有不同节奏 |
| 持续 | 吮吸模式 5，持续吮吸 |
| 弱 / 中 / 强 | 吮吸强度，切换后立刻生效 |
| 振动滑块 | 振动强度 0-10 |
| 停止 | 停止所有动作 |

### AI 控制模式

开启"AI 控制"后，AI 回复时会自动附带玩具指令。

- **剧本模式**：AI 回复结束后播放一段预设动作序列（5-15 步，总时长 ≤30 秒）
- **实时模式**：AI 回复过程中逐步插入控制指令，随内容实时响应
- **氛围自驱模式**：AI 根据对话情境自动周期性触发玩具动作，无需用户每次手动触发

---

## 数据存储

所有数据（对话历史、设置、记忆）均保存在**本地浏览器 localStorage**，不上传任何地方。图片 base64 不持久化（刷新后图片历史不显示，但不影响对话功能）。

---

## 部署到服务器（可选）

> 本地使用无需此步骤，直接双击 HTML 文件打开即可。

如果你希望在任何设备上通过浏览器访问，或分享给他人使用，可以将 HTML 文件部署到静态服务器。

### 方式一：直接上传静态文件（最简单）

适合有虚拟主机、对象存储或静态托管服务的情况。

将 `claude-chat-v16_2_2.html` 上传到以下任一平台即可通过链接访问：

- **Cloudflare Pages**：拖拽上传，免费，自带 CDN
- **Vercel / Netlify**：拖拽或 Git 部署，免费
- **GitHub Pages**：推送到仓库后开启 Pages 功能
- **阿里云 OSS / 腾讯云 COS**：开启静态网站托管，上传文件即可

### 方式二：用 Nginx 部署到 VPS

适合有自己服务器的情况。

```bash
# 将 HTML 文件上传到服务器
scp claude-chat-v16_2_2.html user@your-server:/var/www/html/

# 安装 Nginx（如未安装）
sudo apt install nginx

# Nginx 默认会托管 /var/www/html/ 下的文件
# 访问 http://your-server-ip/claude-chat-v16_2_2.html 即可
```

如需绑定域名并启用 HTTPS，可用 Certbot 申请免费证书：

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

### 方式三：PM2 + Node.js 静态服务（云服务器长期运行）

适合有云服务器、用 SFTP 传文件、希望服务一直在线的情况。

**第一步：安装依赖（只需一次）**

```bash
# 安装 Node.js（如未安装）
sudo apt install nodejs npm

# 全局安装 http-server 和 pm2
npm install -g http-server pm2
```

**第二步：上传文件**

用 Termius、FileZilla 等 SFTP 工具将 `claude-chat-v16_2_2.html` 拖入服务器目录，例如 `/var/www/chat/`。

**第三步：用 PM2 启动并保活**

```bash
# 进入文件所在目录
cd /var/www/chat

# 用 pm2 启动静态服务，监听 8080 端口
pm2 start http-server -- -p 8080

# 设置开机自启
pm2 save
pm2 startup
```

启动后访问 `http://你的服务器IP:8080/claude-chat-v16_2_2.html` 即可。

**常用 PM2 命令**

```bash
pm2 list          # 查看运行中的服务
pm2 restart all   # 重启所有服务
pm2 stop all      # 停止所有服务
pm2 logs          # 查看日志
```

**可选：用 Nginx 反代并绑定域名**

如果希望通过域名访问并启用 HTTPS，可以在 PM2 前面加一层 Nginx：

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

然后用 Certbot 申请证书：

```bash
sudo certbot --nginx -d yourdomain.com
```

### 方式四：Python 临时服务器（局域网共享）

适合临时在局域网内共享给其他设备使用：

```bash
# 在 HTML 文件所在目录执行
python -m http.server 8080
```

然后同一 WiFi 下的设备访问 `http://你的电脑IP:8080/claude-chat-v16_2_2.html` 即可。

### 注意事项

- 部署后每个用户需要自己填入 API Key，不会共用
- 玩具控制功能需要桥接脚本在**用户本地**运行，服务器部署不影响此功能
- 建议部署后启用 HTTPS，避免浏览器因安全限制阻止 API 请求

---

## 其他注意事项

- API Key 保存在本地浏览器，**不要在公共电脑上使用**
- 玩具控制功能需要桥接脚本在本地运行，关闭脚本后自动断开
- 使用 OpenAI 兼容接口时，部分功能（如工具调用格式）可能有差异
