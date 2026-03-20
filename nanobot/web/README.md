# nanobot Web UI

基于 nanobot 的 Web 界面，通过浏览器访问和管理你的个人 AI 助手。

## 功能特性

### 📊 Dashboard
- 系统状态概览
- Provider 配置状态
- 渠道启用状态
- 定时任务计数
- 心跳任务状态

### 💬 对话
- 多轮对话支持
- 流式响应（类似 DeepSeek 网页版）
- 会话管理
- Markdown 渲染
- 代码高亮显示

### 📡 渠道管理
- 查看所有可用渠道
- 启用/禁用渠道
- 渠道配置查看

### 📁 会话管理
- 查看所有对话会话
- 删除历史会话
- 切换到指定会话

### ⏰ 定时任务
- 查看定时任务列表
- 创建新任务（支持 Cron 表达式和间隔秒数）
- 手动触发任务
- 删除任务

### ⚙️ 系统设置
- Agent 配置查看
- 模型设置
- 工作目录信息

## 安装

### 安装 Web UI 依赖

```bash
# 安装 nanobot 并包含 Web UI 依赖
pip install nanobot-ai[web]

# 或者从源码安装
pip install -e ".[web]"
```

### 依赖说明

Web UI 需要以下额外依赖：
- `fastapi` - Web 框架
- `uvicorn` - ASGI 服务器
- `sse-starlette` - SSE 流式响应支持

## 使用方法

### 方法 1: 独立启动 Web UI

```bash
# 使用默认端口 18791
nanobot web

# 指定端口
nanobot web --port 8080

# 指定主机和端口
nanobot web --host 0.0.0.0 --port 8080

# 指定配置文件
nanobot web --config /path/to/config.json
```

### 方法 2: 与 Gateway 一起启动

```bash
# 启动 gateway 并同时启用 Web UI
nanobot gateway --web --web-port 18791
```

### 访问 Web 界面

启动后，在浏览器中访问：

```
http://localhost:18791
```

## API 端点

### REST API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/status` | GET | 获取系统状态 |
| `/api/config` | GET | 获取当前配置 |
| `/api/config` | POST | 更新配置 |
| `/api/channels` | GET | 获取渠道列表 |
| `/api/channels/{name}` | POST | 启用/禁用渠道 |
| `/api/sessions` | GET | 获取会话列表 |
| `/api/sessions/{key}` | GET | 获取会话详情 |
| `/api/sessions/{key}` | DELETE | 删除会话 |
| `/api/chat` | POST | 发送消息（SSE 流式） |
| `/api/cron/jobs` | GET | 获取定时任务列表 |
| `/api/cron/jobs` | POST | 创建定时任务 |
| `/api/cron/jobs/{id}` | DELETE | 删除定时任务 |
| `/api/cron/jobs/{id}/run` | POST | 手动执行任务 |
| `/api/heartbeat` | GET | 获取心跳状态 |
| `/api/heartbeat/trigger` | POST | 手动触发心跳 |

### WebSocket API

| 端点 | 描述 |
|------|------|
| `/ws/chat/{session_key}` | 实时对话 WebSocket |
| `/ws/events` | 系统事件 WebSocket |

## 项目结构

```
nanobot/web/
├── __init__.py          # 包初始化
├── app.py               # FastAPI 应用入口
└── static/
    └── index.html       # 前端页面（单页应用）
```

## 前端说明

前端采用纯 HTML/JS/CSS 实现，无需构建工具：

- **CSS**: 自定义样式（深色主题，类似 DeepSeek 风格）
- **JavaScript**: 原生 ES6+，无框架依赖
- **布局**: 响应式设计，支持移动端

### 页面结构

- **Sidebar**: 导航菜单（Dashboard、对话、渠道管理、会话管理、定时任务、系统设置）
- **Top Bar**: 页面标题和在线状态
- **Main Content**: 各页面内容区域

### 对话功能

- 使用 SSE（Server-Sent Events）接收流式响应
- 支持 Markdown 格式渲染
- 支持代码块高亮
- 打字动画效果

## 截图说明

### Dashboard
显示系统运行状态、模型信息、定时任务数量、心跳状态，以及 Provider 和渠道的启用状态。

### 对话
类似 DeepSeek 的对话界面，左侧为会话列表，中间为对话区域，底部为输入框。

### 渠道管理
卡片式展示所有可用渠道，支持一键启用/禁用。

## 故障排除

### Web UI 无法启动

1. 检查是否安装了 web 依赖：`pip install nanobot-ai[web]`
2. 检查端口是否被占用：`nanobot web --port 8080`
3. 查看配置文件是否正确：`~/.nanobot/config.json`

### 对话无响应

1. 检查 API Key 是否配置正确
2. 检查模型配置是否有效
3. 查看网关日志获取详细错误信息

### 静态文件加载失败

确保 `nanobot/web/static/index.html` 文件存在。

## 开发指南

### 添加新的 API 端点

在 `nanobot/web/app.py` 中添加路由：

```python
@app.get("/api/my-endpoint")
async def my_endpoint():
    return {"message": "Hello"}
```

### 修改前端样式

直接编辑 `nanobot/web/static/index.html` 中的 `<style>` 部分。

### 添加新页面

1. 在 HTML 中添加新的 `<div class="page">` 元素
2. 在 JavaScript 中添加导航和数据加载逻辑

## 安全注意事项

⚠️ **重要**: Web UI 默认允许所有来源的 CORS 请求，仅建议在受信任的网络环境中使用。

生产环境部署建议：
1. 配置反向代理（如 Nginx）
2. 启用 HTTPS
3. 添加认证机制
4. 限制访问 IP 范围

## 许可证

MIT License
