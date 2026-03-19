# nanobot 代码库完整文档

本文档详细记录了 nanobot 项目的所有文件、类、函数及其功能。

---

## 目录

1. [入口文件](#1-入口文件)
2. [CLI 模块](#2-cli-模块)
3. [Agent 模块](#3-agent-模块)
4. [消息总线模块](#4-消息总线模块)
5. [Channel 模块](#5-channel-模块)
6. [Provider 模块](#6-provider-模块)
7. [Session 模块](#7-session-模块)
8. [Config 模块](#8-config-模块)
9. [Cron 模块](#9-cron-模块)
10. [Heartbeat 模块](#10-heartbeat-模块)
11. [Utils 模块](#11-utils-模块)
12. [数据流转示例](#12-数据流转示例)

---

## 1. 入口文件

### 1.1 `__init__.py`

**功能**: 包初始化文件，定义包版本信息。

**内容**:
```python
"""nanobot - minimalistic ai agent framework."""

__version__ = "0.1.4.post4"
```

---

### 1.2 `__main__.py`

**功能**: Python `-m nanobot` 执行入口。

**内容**:
```python
"""Entry point for python -m nanobot."""

from nanobot.cli.commands import app

if __name__ == "__main__":
    app()
```

---

## 2. CLI 模块

### 2.1 `cli/commands.py`

**功能**: CLI 命令入口，提供 agent、gateway、onboard 三个主要命令。

#### `app` (Typer 应用)
Typer CLI 应用实例，包含所有子命令。

#### `agent` 命令
**签名**: `async def agent(message: str | None = None, workspace: str | None = None, model: str | None = None, provider: str | None = None, max_tokens: int | None = None, context_window_tokens: int | None = None, reasoning_effort: str | None = None, system_prompt_file: str | None = None, attach: bool = False)`

**功能**: 交互式 CLI 模式或单条消息模式。

**参数**:
- `message`: 可选，单条消息内容
- `workspace`: 工作区路径
- `model`: 模型名称
- `provider`: LLM 提供商
- `max_tokens`: 最大生成 token 数
- `context_window_tokens`: 上下文窗口大小
- `reasoning_effort`: 推理努力程度
- `system_prompt_file`: 自定义系统提示文件
- `attach`: 是否附加到运行中的 gateway

**执行流程**:
1. 加载配置
2. 创建 Provider
3. 创建 MessageBus
4. 创建 AgentLoop
5. 启动交互循环或发送单条消息

---

#### `gateway` 命令
**签名**: `async def gateway(workspace: str | None = None, model: str | None = None, provider: str | None = None, max_tokens: int | None = None, context_window_tokens: int | None = None, reasoning_effort: str | None = None, system_prompt_file: str | None = None)`

**功能**: 服务器模式，启动所有配置的 Channel 和 Agent。

**参数**: 同 `agent` 命令（除 attach 外）。

**执行流程**:
1. 加载配置
2. 创建 Provider
3. 创建 MessageBus
4. 创建 AgentLoop
5. 创建 ChannelManager
6. 创建 CronService 和 HeartbeatService
7. 并发启动所有服务

---

#### `onboard` 命令
**签名**: `async def onboard()`

**功能**: 初始化配置和工作区。

**执行流程**:
1. 检查是否已有配置
2. 交互式询问用户偏好
3. 选择 LLM 提供商和模型
4. 配置 API 密钥
5. 创建默认工作区文件（AGENTS.md、SOUL.md、USER.md 等）
6. 保存配置

---

#### `_load_runtime_config()`
**签名**: `def _load_runtime_config(cli_workspace: str | None = None, cli_model: str | None = None, ...) -> Config`

**功能**: 加载运行时配置，应用 CLI 参数覆盖。

**参数**: 各种 CLI 参数覆盖选项。

**返回**: `Config` 配置对象。

---

#### `_make_provider()`
**签名**: `def _make_provider(config: Config, workspace: Path) -> LLMProvider`

**功能**: 根据配置创建 LLM Provider 实例。

**参数**:
- `config`: 配置对象
- `workspace`: 工作区路径

**返回**: `LLMProvider` 实例。

---

#### `run_interactive()`
**签名**: `async def run_interactive(agent_loop: AgentLoop, bus: MessageBus, workspace: Path)`

**功能**: 运行交互式 CLI 会话。

**参数**:
- `agent_loop`: AgentLoop 实例
- `bus`: MessageBus 实例
- `workspace`: 工作区路径

**执行流程**:
1. 创建三个异步任务：
   - `_read_interactive_input_async()`: 读取用户输入
   - `agent_loop.run()`: Agent 循环监听消息
   - `_consume_outbound_messages()`: 消费并显示回复
2. 并发运行直到用户退出

---

#### `_read_interactive_input_async()`
**签名**: `async def _read_interactive_input_async(bus: MessageBus, workspace: Path)`

**功能**: 使用 prompt_toolkit 异步读取用户输入。

**参数**:
- `bus`: MessageBus 实例
- `workspace`: 工作区路径

**执行流程**:
1. 显示欢迎信息
2. 循环读取用户输入
3. 创建 InboundMessage 并发布到总线
4. 处理退出命令（/quit、/exit）

---

#### `_consume_outbound_messages()`
**签名**: `async def _consume_outbound_messages(bus: MessageBus)`

**功能**: 消费总线上的出站消息并显示。

**参数**:
- `bus`: MessageBus 实例

**执行流程**:
1. 循环从总线获取 OutboundMessage
2. 打印到终端

---

---

## 3. Agent 模块

### 3.1 `agent/loop.py`

**功能**: Agent 核心循环引擎。

#### `AgentLoop` 类

**属性**:
- `bus`: MessageBus 实例
- `provider`: LLMProvider 实例
- `workspace`: 工作区路径
- `max_tokens`: 最大生成 token 数
- `context_window_tokens`: 上下文窗口大小
- `reasoning_effort`: 推理努力程度
- `system_prompt_file`: 自定义系统提示
- `max_iterations`: 最大迭代次数（默认 100）
- `tool_registry`: ToolRegistry 实例
- `session_manager`: SessionManager 实例

---

#### `__init__()`
**签名**: `def __init__(self, bus: MessageBus, provider: LLMProvider, workspace: Path, max_tokens: int, context_window_tokens: int, reasoning_effort: str, system_prompt_file: str | None, max_iterations: int = 100)`

**功能**: 初始化 AgentLoop。

**参数**:
- `bus`: 消息总线
- `provider`: LLM 提供商
- `workspace`: 工作区路径
- `max_tokens`: 最大 token 数
- `context_window_tokens`: 上下文窗口大小
- `reasoning_effort`: 推理努力
- `system_prompt_file`: 系统提示文件
- `max_iterations`: 最大迭代次数

---

#### `run()`
**签名**: `async def run()`

**功能**: 启动 Agent 循环。

**执行流程**:
1. 注册默认工具
2. 加载技能
3. 循环监听总线消息
4. 调用 `_process_message()` 处理消息

---

#### `_process_message()`
**签名**: `async def _process_message(msg: InboundMessage)`

**功能**: 处理单条入站消息。

**参数**:
- `msg`: InboundMessage 实例

**执行流程**:
1. 获取或创建会话
2. 构建上下文（系统提示 + 历史消息）
3. 调用 `_run_agent_loop()`
4. 保存会话

---

#### `_run_agent_loop()`
**签名**: `async def _run_agent_loop(session: Session, context_messages: list[dict], msg: InboundMessage) -> str | None`

**功能**: 核心迭代循环，处理工具调用。

**参数**:
- `session`: 会话对象
- `context_messages`: 上下文消息列表
- `msg`: 入站消息

**返回**: 最终回复或 None。

**执行流程**:
1. 循环调用 `provider.chat_with_retry()`
2. 检查是否有工具调用
3. 执行工具并收集结果
4. 添加工具结果到消息历史
5. 重复直到没有工具调用
6. 返回最终回复

---

#### `process_direct()`
**签名**: `async def process_direct(message: str) -> str`

**功能**: CLI 直接调用接口（用于单条消息模式）。

**参数**:
- `message`: 用户消息

**返回**: Agent 回复。

---

#### `_register_default_tools()`
**签名**: `def _register_default_tools()`

**功能**: 注册内置工具到 ToolRegistry。

**注册的工具**:
- `read_file`, `write_file`, `edit_file`, `list_dir`
- `exec`
- `web_search`, `web_fetch`
- `message`
- `spawn`
- `cron`
- `mcp_*` (动态)

---

### 3.2 `agent/context.py`

**功能**: 构建系统提示和消息上下文。

#### `ContextBuilder` 类

---

#### `build_system_prompt()`
**签名**: `async def build_system_prompt(workspace: Path, system_prompt_file: str | None) -> str`

**功能**: 构建完整的系统提示。

**参数**:
- `workspace`: 工作区路径
- `system_prompt_file`: 自定义系统提示文件

**返回**: 系统提示字符串。

**系统提示结构**:
```
# nanobot 🐈
[身份说明]

## Bootstrap 文件
- AGENTS.md - 行为准则
- SOUL.md - 个性设定
- USER.md - 用户偏好
- TOOLS.md - 工具说明

## Memory
- MEMORY.md - 长期记忆
- HISTORY.md - 历史摘要

## Active Skills
- 始终加载的技能

## Skills Summary
- 可用技能列表
```

---

#### `build_messages()`
**签名**: `def build_messages(system_prompt: str, session: Session, msg: InboundMessage) -> list[dict]`

**功能**: 构建完整的消息历史。

**参数**:
- `system_prompt`: 系统提示
- `session`: 会话对象
- `msg`: 入站消息

**返回**: 消息列表（OpenAI 格式）。

---

### 3.3 `agent/memory.py`

**功能**: 记忆管理和压缩系统。

#### `MemoryConsolidator` 类

**属性**:
- `session_manager`: SessionManager 实例
- `provider`: LLMProvider 实例

---

#### `maybe_consolidate_by_tokens()`
**签名**: `async def maybe_consolidate_by_tokens(session: Session, context_window_tokens: int) -> bool`

**功能**: 检查会话 token 数，超过阈值时触发压缩。

**参数**:
- `session`: 会话对象
- `context_window_tokens`: 上下文窗口大小

**返回**: 是否执行了压缩。

---

#### `consolidate_messages()`
**签名**: `async def consolidate_messages(messages: list[dict], boundary: int) -> str`

**功能**: 调用 LLM 将消息压缩为摘要。

**参数**:
- `messages`: 消息列表
- `boundary`: 压缩边界（之前的消息数量）

**返回**: 压缩后的摘要。

---

#### `pick_consolidation_boundary()`
**签名**: `def pick_consolidation_boundary(messages: list[dict]) -> int`

**功能**: 选择合适的压缩边界（用户消息边界）。

**参数**:
- `messages`: 消息列表

**返回**: 边界索引。

---

### 3.4 `agent/skills.py`

**功能**: 技能系统，动态加载 SKILL.md 文件。

#### `SkillManager` 类

---

#### `load_skills()`
**签名**: `async def load_skills(workspace: Path) -> list[str]`

**功能**: 加载工作区和内置技能。

**参数**:
- `workspace`: 工作区路径

**返回**: 加载的技能列表。

**加载顺序**:
1. 工作区技能（`workspace/skills/`）
2. 内置技能（`nanobot/skills/`）

---

#### `_check_dependencies()`
**签名**: `def _check_dependencies(skill_path: Path) -> tuple[bool, str | None]`

**功能**: 检查技能依赖是否满足。

**参数**:
- `skill_path`: SKILL.md 文件路径

**返回**: (是否满足，错误信息)。

---

### 3.5 `agent/subagent.py`

**功能**: 子代理系统，用于后台任务。

#### `SubagentTask` 类

---

#### `__init__()`
**签名**: `def __init__(self, bus: MessageBus, provider: LLMProvider, workspace: Path, goal: str, context: str)`

**功能**: 初始化子代理任务。

**参数**:
- `bus`: 消息总线
- `provider`: LLM 提供商
- `workspace`: 工作区路径
- `goal`: 任务目标
- `context`: 任务上下文

---

#### `run()`
**签名**: `async def run()`

**功能**: 运行子代理任务。

**执行流程**:
1. 创建独立的 AgentLoop
2. 发送目标消息
3. 等待任务完成
4. 返回结果

---

---

## 4. 消息总线模块

### 4.1 `bus/queue.py`

**功能**: 异步消息队列实现。

#### `MessageBus` 类

**属性**:
- `_inbound_queue`: asyncio.Queue[InboundMessage]
- `_outbound_queue`: asyncio.Queue[OutboundMessage]

---

#### `publish_inbound()`
**签名**: `async def publish_inbound(msg: InboundMessage)`

**功能**: 发布入站消息。

**参数**:
- `msg`: InboundMessage 实例

---

#### `publish_outbound()`
**签名**: `async def publish_outbound(msg: OutboundMessage)`

**功能**: 发布出站消息。

**参数**:
- `msg`: OutboundMessage 实例

---

#### `get_inbound()`
**签名**: `async def get_inbound() -> InboundMessage`

**功能**: 获取入站消息（阻塞直到有消息）。

**返回**: InboundMessage 实例。

---

#### `get_outbound()`
**签名**: `async def get_outbound() -> OutboundMessage`

**功能**: 获取出站消息（阻塞直到有消息）。

**返回**: OutboundMessage 实例。

---

### 4.2 `bus/events.py`

**功能**: 定义消息总线事件类型。

#### `InboundMessage` dataclass

**属性**:
- `channel`: str - 来源渠道（telegram, discord, slack, whatsapp）
- `sender_id`: str - 发送者 ID
- `chat_id`: str - 聊天/频道 ID
- `content`: str - 消息内容
- `timestamp`: datetime - 时间戳（默认现在）
- `media`: list[str] - 媒体 URL 列表
- `metadata`: dict[str, Any] - 渠道特定元数据
- `session_key_override`: str | None - 可选的会话键覆盖

**方法**:
- `session_key`: property - 返回 `f"{channel}:{chat_id}"`

---

#### `OutboundMessage` dataclass

**属性**:
- `channel`: str - 目标渠道
- `chat_id`: str - 目标聊天 ID
- `content`: str - 消息内容
- `reply_to`: str | None - 回复的目标消息 ID
- `media`: list[str] - 媒体 URL 列表
- `metadata`: dict[str, Any] - 元数据

---

---

## 5. Channel 模块

### 5.1 `channels/base.py`

**功能**: Channel 抽象基类。

#### `BaseChannel` 抽象类

**属性**:
- `name`: str - 渠道名称
- `config`: dict - 配置字典

---

#### `start()`
**签名**: `async def start() -> None`

**功能**: 启动渠道服务。

---

#### `stop()`
**签名**: `async def stop() -> None`

**功能**: 停止渠道服务。

---

#### `send()`
**签名**: `async def send(msg: OutboundMessage) -> None`

**功能**: 发送消息。

**参数**:
- `msg`: OutboundMessage 实例

---

#### `poll()`
**签名**: `async def poll() -> InboundMessage | None`

**功能**: 轮询接收消息。

**返回**: InboundMessage 或 None。

---

### 5.2 `channels/manager.py`

**功能**: Channel 管理器，协调消息路由。

#### `ChannelManager` 类

**属性**:
- `channels`: list[BaseChannel] - 启用的 Channel 列表
- `bus`: MessageBus - 消息总线

---

#### `__init__()`
**签名**: `def __init__(self, config: Config, bus: MessageBus)`

**功能**: 初始化管理器。

**参数**:
- `config`: 配置对象
- `bus`: 消息总线

---

#### `start_all()`
**签名**: `async def start_all()`

**功能**: 启动所有 Channel。

**执行流程**:
1. 并发启动所有 Channel 的 `start()`
2. 启动 `_dispatch_outbound()` 任务

---

#### `stop_all()`
**签名**: `async def stop_all()`

**功能**: 停止所有 Channel。

---

#### `_dispatch_outbound()`
**签名**: `async def _dispatch_outbound()`

**功能**: 路由出站消息到对应 Channel。

**执行流程**:
1. 循环从总线获取 OutboundMessage
2. 根据 `msg.channel` 找到对应 Channel
3. 调用 `channel.send(msg)`

---

### 5.3 `channels/registry.py`

**功能**: Channel 注册表，动态发现 Channel 实现。

#### `discover_channels()`
**签名**: `def discover_channels() -> dict[str, type[BaseChannel]]`

**功能**: 发现所有注册的 Channel。

**返回**: {name: ChannelClass} 字典。

---

### 5.4 `channels/telegram.py` (示例)

**功能**: Telegram Channel 实现。

#### `TelegramChannel` 类

**继承**: `BaseChannel`

**属性**:
- `bot_token`: str - Bot API Token
- `allowed_chat_ids`: list[int] - 允许的聊天 ID 列表

---

#### `start()`
**签名**: `async def start()`

**功能**: 启动 Telegram Bot 轮询。

---

#### `stop()`
**签名**: `async def stop()`

**功能**: 停止轮询。

---

#### `send()`
**签名**: `async def send(msg: OutboundMessage)`

**功能**: 通过 Telegram Bot API 发送消息。

---

#### `poll()`
**签名**: `async def poll() -> InboundMessage | None`

**功能**: 轮询 Telegram 更新并转换为 InboundMessage。

---

---

## 6. Provider 模块

### 6.1 `providers/base.py`

**功能**: LLM Provider 抽象基类。

#### `LLMProvider` 抽象类

---

#### `chat()`
**签名**: `async def chat(messages: list[dict], tools: list[dict] | None = None, max_tokens: int | None = None, temperature: float | None = None) -> LLMResponse`

**功能**: 调用 LLM。

**参数**:
- `messages`: 消息列表（OpenAI 格式）
- `tools`: 工具列表（可选）
- `max_tokens`: 最大 token 数
- `temperature`: 温度参数

**返回**: `LLMResponse` 实例。

---

#### `chat_with_retry()`
**签名**: `async def chat_with_retry(..., retries: int = 3, delay: float = 1.0) -> LLMResponse`

**功能**: 带自动重试的 chat 方法。

**参数**: 同 `chat()`，加上：
- `retries`: 重试次数
- `delay`: 重试延迟

---

#### `get_default_model()`
**签名**: `def get_default_model() -> str`

**功能**: 获取默认模型名称。

**返回**: 模型名称字符串。

---

#### `LLMResponse` dataclass

**属性**:
- `content`: str | None - 文本回复
- `tool_calls`: list[ToolCall] | None - 工具调用列表
- `finish_reason`: str | None - 结束原因
- `usage`: dict | None - 使用统计
- `reasoning_content`: str | None - 推理内容（某些模型）
- `thinking_blocks`: list[dict] | None - 思考块（某些模型）

---

#### `GenerationSettings` dataclass

**属性**:
- `temperature`: float - 温度
- `max_tokens`: int - 最大 token 数
- `reasoning_effort`: str - 推理努力

---

### 6.2 `providers/litellm_provider.py`

**功能**: LiteLLM Provider 实现。

#### `LiteLLMProvider` 类

**继承**: `LLMProvider`

**属性**:
- `model`: str - 模型名称
- `api_key`: str | None - API 密钥
- `api_base`: str | None - API 地址

---

#### `__init__()`
**签名**: `def __init__(self, model: str, api_key: str | None = None, api_base: str | None = None, **kwargs)`

**功能**: 初始化 Provider。

---

#### `_resolve_model()`
**签名**: `def _resolve_model(model: str) -> str`

**功能**: 解析模型名，应用提供商前缀。

**参数**:
- `model`: 模型名称（如 `claude-sonnet-4-5`）

**返回**: 完整模型名（如 `anthropic/claude-sonnet-4-5`）。

---

#### `_apply_cache_control()`
**签名**: `def _apply_cache_control(messages: list[dict]) -> list[dict]`

**功能**: 应用 prompt caching（针对 Anthropic 等）。

**参数**:
- `messages`: 消息列表

**返回**: 添加了缓存控制的 message 列表。

---

#### `_parse_response()`
**签名**: `def _parse_response(response) -> LLMResponse`

**功能**: 解析 LiteLLM 响应。

**参数**:
- `response`: LiteLLM 响应对象

**返回**: `LLMResponse` 实例。

---

### 6.3 `providers/custom_provider.py`

**功能**: 自定义 OpenAI 兼容 Provider。

#### `CustomProvider` 类

**继承**: `LLMProvider`

**属性**:
- `api_key`: str - API 密钥
- `api_base`: str - API 地址
- `model`: str - 模型名称

---

#### `chat()`
**签名**: `async def chat(messages: list[dict], tools: list[dict] | None = None, max_tokens: int | None = None) -> LLMResponse`

**功能**: 使用 `openai.AsyncOpenAI` 直接调用。

---

### 6.4 `providers/azure_openai_provider.py`

**功能**: Azure OpenAI Provider。

#### `AzureOpenAIProvider` 类

**继承**: `LLMProvider`

**属性**:
- `api_key`: str - API 密钥
- `azure_endpoint`: str - Azure 端点
- `deployment_name`: str - 部署名称
- `api_version`: str - API 版本（默认 2024-10-21）

---

#### `chat()`
**签名**: `async def chat(...)`

**功能**: 调用 Azure OpenAI API。

**注意**: 使用 `max_completion_tokens` 代替 `max_tokens`。

---

### 6.5 `providers/openai_codex_provider.py`

**功能**: OpenAI Codex Provider (OAuth)。

#### `OpenAICodexProvider` 类

**继承**: `LLMProvider`

---

#### `_convert_messages()`
**签名**: `def _convert_messages(messages: list[dict]) -> list[dict]`

**功能**: 转换消息为 Codex 格式。

---

#### `_consume_sse()`
**签名**: `async def _consume_sse(response) -> AsyncGenerator[str, None]`

**功能**: 消费 SSE 流式响应。

---

### 6.6 `providers/transcription.py`

**功能**: Groq 语音转写 Provider。

#### `GroqTranscriptionProvider` 类

**继承**: `LLMProvider`

---

#### `transcribe()`
**签名**: `async def transcribe(audio_path: str) -> str`

**功能**: 使用 Groq Whisper API 转录音频。

**参数**:
- `audio_path`: 音频文件路径

**返回**: 转录文本。

---

### 6.7 `providers/registry.py`

**功能**: Provider 注册表，20+ 提供商元数据。

#### `ProviderSpec` dataclass

**属性**:
- `name`: str - 提供商名称
- `keywords`: list[str] - 模型名关键词
- `env_key`: str - 环境变量名
- `display_name`: str - 显示名称
- `litellm_prefix`: str | None - LiteLLM 前缀
- `is_gateway`: bool - 是否需要网关
- `is_local`: bool - 是否本地部署
- `is_oauth`: bool - 是否 OAuth 认证

---

#### `PROVIDERS` tuple

**功能**: 所有注册提供商元数据。

**包括**: OpenRouter, AiHubMix, Anthropic, OpenAI, DeepSeek, Gemini, Zhipu, DashScope, Moonshot, Baichuan, Minimax, Qwen, Ollama, Azure OpenAI, OpenAI Codex, GitHub Copilot 等。

---

#### `find_by_model()`
**签名**: `def find_by_model(model: str) -> ProviderSpec | None`

**功能**: 根据模型名查找提供商。

---

#### `find_gateway()`
**签名**: `def find_gateway(model: str) -> ProviderSpec | None`

**功能**: 查找需要网关的提供商。

---

#### `find_by_name()`
**签名**: `def find_by_name(name: str) -> ProviderSpec | None`

**功能**: 根据名称查找提供商。

---

---

## 7. Session 模块

### 7.1 `session/manager.py`

**功能**: 会话管理器。

#### `Session` dataclass

**属性**:
- `key`: str - 会话键（`channel:chat_id`）
- `messages`: list[dict] - 消息历史（JSONL 格式）
- `created_at`: float - 创建时间戳
- `updated_at`: float - 更新时间戳
- `metadata`: dict - 元数据
- `last_consolidated`: int - 已压缩的偏移量

---

#### `SessionManager` 类

**属性**:
- `session_dir`: Path - 会话存储目录
- `_cache`: dict[str, Session] - 内存缓存

---

#### `get_or_create()`
**签名**: `def get_or_create(key: str) -> Session`

**功能**: 获取或创建会话。

**参数**:
- `key`: 会话键

**返回**: Session 实例。

---

#### `_load()`
**签名**: `def _load(key: str) -> Session | None`

**功能**: 从磁盘加载会话。

**参数**:
- `key`: 会话键

**返回**: Session 或 None。

---

#### `save()`
**签名**: `def save(session: Session) -> None`

**功能**: 保存会话到磁盘。

**参数**:
- `session`: Session 实例

---

#### `list_sessions()`
**签名**: `def list_sessions() -> list[str]`

**功能**: 列出所有会话键。

**返回**: 会话键列表。

---

---

## 8. Config 模块

### 8.1 `config/schema.py`

**功能**: Pydantic 配置模型。

#### `Config` 类

**继承**: `pydantic.BaseModel`

**属性**:
- `agents`: dict - Agent 配置
- `channels`: dict - Channel 配置
- `providers`: ProvidersConfig - 提供商配置
- `gateway`: dict - Gateway 配置
- `tools`: dict - 工具配置

---

#### `ProvidersConfig` 类

**继承**: `pydantic.BaseModel`

**属性**: 20+ 提供商配置字段（anthropic, openai, deepseek, etc.）

每个提供商配置包含：
- `api_key`: str | None
- `api_base`: str | None
- `model`: str | None

---

#### `_match_provider()`
**签名**: `static def _match_provider(model: str, providers: ProvidersConfig) -> str | None`

**功能**: 自动匹配提供商。

**参数**:
- `model`: 模型名称
- `providers`: 提供商配置

**返回**: 匹配的提供商名称。

---

### 8.2 `config/loader.py`

**功能**: 配置加载工具。

#### `load_config()`
**签名**: `def load_config() -> Config`

**功能**: 从文件加载配置或创建默认。

**返回**: Config 实例。

---

#### `save_config()`
**签名**: `def save_config(config: Config) -> None`

**功能**: 保存配置到文件。

---

#### `_migrate_config()`
**签名**: `def _migrate_config(data: dict) -> dict`

**功能**: 迁移旧版配置格式。

---

### 8.3 `config/paths.py`

**功能**: 运行时路径辅助函数。

#### `get_data_dir()`
**签名**: `def get_data_dir() -> Path`

**功能**: 获取数据目录（`~/.nanobot`）。

---

#### `get_runtime_subdir()`
**签名**: `def get_runtime_subdir(name: str) -> Path`

**功能**: 获取运行时子目录。

---

#### `get_media_dir()`
**签名**: `def get_media_dir() -> Path`

**功能**: 获取媒体存储目录。

---

#### `get_cron_dir()`
**签名**: `def get_cron_dir() -> Path`

**功能**: 获取 Cron 存储目录。

---

#### `get_logs_dir()`
**签名**: `def get_logs_dir() -> Path`

**功能**: 获取日志目录。

---

#### `get_workspace_path()`
**签名**: `def get_workspace_path(workspace: str | None) -> Path`

**功能**: 获取工作区路径。

---

#### `get_cli_history_path()`
**签名**: `def get_cli_history_path() -> Path`

**功能**: 获取 CLI 历史文件路径。

---

---

## 9. Cron 模块

### 9.1 `cron/types.py`

**功能**: Cron 类型定义。

#### `CronSchedule` dataclass

**属性**:
- `kind`: str - 调度类型（`at`, `every`, `cron`）
- `at_ms`: int | None - 一次性执行时间戳
- `every_ms`: int | None - 间隔毫秒数
- `expr`: str | None - Cron 表达式
- `tz`: str | None - 时区（仅 cron）

---

#### `CronPayload` dataclass

**属性**:
- `kind`: str - 负载类型（默认 `agent_turn`）
- `message`: str - 消息内容
- `deliver`: bool - 是否发送消息
- `channel`: str | None - 目标渠道
- `to`: str | None - 目标聊天 ID

---

#### `CronJob` dataclass

**属性**:
- `id`: str - 任务 ID
- `name`: str - 任务名称
- `enabled`: bool - 是否启用
- `schedule`: CronSchedule - 调度配置
- `payload`: CronPayload - 负载配置
- `state`: CronJobState - 状态
- `created_at_ms`: int - 创建时间戳
- `updated_at_ms`: int - 更新时间戳
- `delete_after_run`: bool - 运行后是否删除

---

#### `CronJobState` dataclass

**属性**:
- `next_run_at_ms`: int | None - 下次运行时间
- `last_run_at_ms`: int | None - 上次运行时间
- `last_status`: str | None - 最后状态（`ok`, `error`）
- `last_error`: str | None - 最后错误信息

---

#### `CronStore` dataclass

**属性**:
- `version`: int - 存储版本
- `jobs`: list[CronJob] - 任务列表

---

### 9.2 `cron/service.py`

**功能**: Cron 服务实现。

#### `CronService` 类

**属性**:
- `store_path`: Path - 存储文件路径
- `on_job`: Callable | None - 任务执行回调
- `_store`: CronStore | None - 内存缓存
- `_last_mtime`: float - 最后修改时间
- `_timer_task`: asyncio.Task | None - 定时器任务
- `_running`: bool - 运行状态

---

#### `__init__()`
**签名**: `def __init__(store_path: Path, on_job: Callable | None = None)`

**功能**: 初始化服务。

---

#### `start()`
**签名**: `async def start()`

**功能**: 启动 Cron 服务。

**执行流程**:
1. 加载存储
2. 重新计算下次运行时间
3. 保存存储
4. 启动定时器

---

#### `stop()`
**签名**: `def stop()`

**功能**: 停止服务。

---

#### `_load_store()`
**签名**: `def _load_store() -> CronStore`

**功能**: 加载存储（支持外部修改自动重载）。

---

#### `_save_store()`
**签名**: `def _save_store() -> None`

**功能**: 保存存储到磁盘。

---

#### `_compute_next_run()`
**签名**: `def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None`

**功能**: 计算下次运行时间。

**参数**:
- `schedule`: CronSchedule 实例
- `now_ms`: 当前时间戳（毫秒）

**返回**: 下次运行时间戳或 None。

---

#### `_recompute_next_runs()`
**签名**: `def _recompute_next_runs() -> None`

**功能**: 重新计算所有任务的下次运行时间。

---

#### `_get_next_wake_ms()`
**签名**: `def _get_next_wake_ms() -> int | None`

**功能**: 获取最早的下一次运行时间。

---

#### `_arm_timer()`
**签名**: `def _arm_timer() -> None`

**功能**: 设置定时器。

---

#### `_on_timer()`
**签名**: `async def _on_timer() -> None`

**功能**: 定时器触发处理。

**执行流程**:
1. 加载存储
2. 找出到期的任务
3. 执行任务
4. 保存存储
5. 重新设置定时器

---

#### `_execute_job()`
**签名**: `async def _execute_job(job: CronJob) -> None`

**功能**: 执行单个任务。

**参数**:
- `job`: CronJob 实例

**执行流程**:
1. 调用 `on_job` 回调
2. 更新状态
3. 计算下次运行时间
4. 处理一次性任务（禁用或删除）

---

#### `list_jobs()`
**签名**: `def list_jobs(include_disabled: bool = False) -> list[CronJob]`

**功能**: 列出所有任务。

**参数**:
- `include_disabled`: 是否包括禁用的任务

**返回**: CronJob 列表（按下次运行时间排序）。

---

#### `add_job()`
**签名**: `def add_job(name: str, schedule: CronSchedule, message: str, deliver: bool = False, channel: str | None = None, to: str | None = None, delete_after_run: bool = False) -> CronJob`

**功能**: 添加新任务。

**返回**: 新创建的 CronJob。

---

#### `remove_job()`
**签名**: `def remove_job(job_id: str) -> bool`

**功能**: 删除任务。

**返回**: 是否成功删除。

---

#### `enable_job()`
**签名**: `def enable_job(job_id: str, enabled: bool = True) -> CronJob | None`

**功能**: 启用/禁用任务。

**返回**: CronJob 或 None。

---

#### `run_job()`
**签名**: `async def run_job(job_id: str, force: bool = False) -> bool`

**功能**: 手动运行任务。

**参数**:
- `force`: 是否强制运行（即使禁用）

**返回**: 是否成功运行。

---

#### `status()`
**签名**: `def status() -> dict`

**功能**: 获取服务状态。

**返回**: {enabled, jobs, next_wake_at_ms} 字典。

---

---

## 10. Heartbeat 模块

### 10.1 `heartbeat/service.py`

**功能**: 心跳服务，周期性检查并执行任务。

#### `HeartbeatService` 类

**属性**:
- `workspace`: Path - 工作区路径
- `provider`: LLMProvider - LLM 提供商
- `interval_seconds`: int - 检查间隔
- `on_execute`: Callable | None - 执行回调
- `_running`: bool - 运行状态
- `_task`: asyncio.Task | None - 任务

---

#### `__init__()`
**签名**: `def __init__(workspace: Path, provider: LLMProvider, interval_seconds: int = 60, on_execute: Callable | None = None)`

**功能**: 初始化服务。

---

#### `start()`
**签名**: `async def start()`

**功能**: 启动心跳服务。

**执行流程**:
1. 设置 `_running = True`
2. 启动后台任务 `_run()`

---

#### `stop()`
**签名**: `def stop()`

**功能**: 停止服务。

---

#### `_run()`
**签名**: `async def _run()`

**功能**: 后台循环。

**执行流程**:
1. 循环等待 `interval_seconds`
2. 检查 `HEARTBEAT.md` 文件
3. 调用 `_decide()` 决定是否执行
4. 如果决定执行，调用 `on_execute`

---

#### `_decide()`
**签名**: `async def _decide(task_description: str) -> bool`

**功能**: 调用 LLM 决定是否执行任务。

**参数**:
- `task_description`: 任务描述

**返回**: 是否执行。

**实现方式**: 通过虚拟 tool call 让 LLM 决定。

---

---

## 11. Utils 模块

### 11.1 `utils/helpers.py`

**功能**: 通用工具函数。

#### `estimate_prompt_tokens()`
**签名**: `def estimate_prompt_tokens(messages: list[dict]) -> int`

**功能**: 使用 tiktoken 估计 token 数。

**参数**:
- `messages`: 消息列表

**返回**: 估计的 token 数。

---

#### `estimate_message_tokens()`
**签名**: `def estimate_message_tokens(message: dict) -> int`

**功能**: 估计单条消息的 token 数。

---

#### `sync_workspace_templates()`
**签名**: `def sync_workspace_templates(workspace: Path) -> None`

**功能**: 同步模板文件到工作区。

---

### 11.2 `utils/evaluator.py`

**功能**: 后台任务响应评估。

#### `evaluate_response()`
**签名**: `async def evaluate_response(provider: LLMProvider, context: str, response: str) -> bool`

**功能**: 调用 LLM 决定是否通知用户。

**参数**:
- `provider`: LLM 提供商
- `context`: 上下文
- `response`: 响应内容

**返回**: 是否应该通知用户。

**用途**: 用于 Heartbeat 和 Cron 任务完成后的通知过滤。

---

---

## 12. 工具模块（agent/tools/）

### 12.1 `agent/tools/base.py`

**功能**: 工具抽象基类。

#### `Tool` 抽象类

---

#### `name` (property)
**签名**: `@property @abstractmethod def name() -> str`

**功能**: 工具名称。

---

#### `description` (property)
**签名**: `@property @abstractmethod def description() -> str`

**功能**: 工具描述。

---

#### `parameters` (property)
**签名**: `@property @abstractmethod def parameters() -> dict[str, Any]`

**功能**: JSON Schema 参数定义。

---

#### `execute()`
**签名**: `@abstractmethod async def execute(**kwargs: Any) -> str`

**功能**: 执行工具。

**参数**: 工具特定的参数。

**返回**: 执行结果字符串。

---

#### `cast_params()`
**签名**: `def cast_params(params: dict[str, Any]) -> dict[str, Any]`

**功能**: 参数类型转换。

**参数**:
- `params`: 原始参数字典

**返回**: 转换后的参数字典。

---

#### `validate_params()`
**签名**: `def validate_params(params: dict[str, Any]) -> list[str]`

**功能**: JSON Schema 参数验证。

**参数**:
- `params`: 参数字典

**返回**: 错误列表（空表示验证通过）。

---

#### `to_schema()`
**签名**: `def to_schema() -> dict[str, Any]`

**功能**: 转换为 OpenAI 函数调用格式。

**返回**: {"type": "function", "function": {...}}。

---

### 12.2 `agent/tools/registry.py`

**功能**: 工具注册表。

#### `ToolRegistry` 类

**属性**:
- `_tools`: dict[str, Tool] - 工具字典

---

#### `register()`
**签名**: `def register(tool: Tool) -> None`

**功能**: 注册工具。

---

#### `unregister()`
**签名**: `def unregister(name: str) -> bool`

**功能**: 注销工具。

**返回**: 是否成功注销。

---

#### `get()`
**签名**: `def get(name: str) -> Tool | None`

**功能**: 获取工具实例。

---

#### `execute()`
**签名**: `async def execute(name: str, params: dict[str, Any]) -> str`

**功能**: 执行工具。

**参数**:
- `name`: 工具名称
- `params`: 参数字典

**返回**: 执行结果。

**执行流程**:
1. 获取工具
2. 转换参数
3. 验证参数
4. 执行工具
5. 返回结果或错误

---

#### `get_definitions()`
**签名**: `def get_definitions() -> list[dict]`

**功能**: 获取所有工具的定义（OpenAI 格式）。

**返回**: 工具定义列表。

---

### 12.3 `agent/tools/filesystem.py`

**功能**: 文件操作工具。

#### `ReadFileTool` 类

**方法**:
- `name`: "read_file"
- `description`: 读取文件内容（支持分页）
- `parameters`: {path, offset, limit}
- `execute(path, offset=1, limit=None)`: 读取文件

---

#### `WriteFileTool` 类

**方法**:
- `name`: "write_file"
- `description`: 写入文件
- `parameters`: {path, content}
- `execute(path, content)`: 写入文件

---

#### `EditFileTool` 类

**方法**:
- `name`: "edit_file"
- `description`: 编辑文件（替换 old_text）
- `parameters`: {path, old_text, new_text, replace_all}
- `execute(path, old_text, new_text, replace_all=False)`: 编辑文件

**特性**: 支持模糊匹配（忽略空白差异）

---

#### `ListDirTool` 类

**方法**:
- `name`: "list_dir"
- `description`: 列出目录（支持递归）
- `parameters`: {path, recursive, max_entries}
- `execute(path, recursive=False, max_entries=None)`: 列出目录

**特性**: 自动忽略噪声目录（.git, node_modules, __pycache__ 等）

---

### 12.4 `agent/tools/shell.py`

**功能**: Shell 命令执行工具。

#### `ExecTool` 类

**方法**:
- `name`: "exec"
- `description`: 执行 Shell 命令
- `parameters`: {command, timeout, workdir}
- `execute(command, timeout=60, workdir=None)`: 执行命令

**安全检查**: `_guard_command()` 阻止危险命令（rm -rf, format, dd 等）

---

### 12.5 `agent/tools/web.py`

**功能**: 网络搜索和网页抓取工具。

#### `WebSearchTool` 类

**方法**:
- `name`: "web_search"
- `description`: 网络搜索
- `parameters`: {query, provider, num_results}
- `execute(query, provider="brave", num_results=5)`: 搜索

**支持的提供商**: Brave, Tavily, DuckDuckGo, SearXNG, Jina

---

#### `WebFetchTool` 类

**方法**:
- `name`: "web_fetch"
- `description`: 抓取网页内容
- `parameters`: {url}
- `execute(url)`: 抓取网页

**模式**: Jina Reader + Readability 双模式

---

### 12.6 `agent/tools/message.py`

**功能**: 消息发送工具。

#### `MessageTool` 类

**方法**:
- `name`: "message"
- `description`: 发送消息
- `parameters`: {text}
- `execute(text)`: 发送消息

**上下文管理**:
- `set_context(channel, chat_id)`: 设置上下文
- `start_turn()`: 重置每轮发送跟踪

---

### 12.7 `agent/tools/spawn.py`

**功能**: 子代理生成工具。

#### `SpawnTool` 类

**方法**:
- `name`: "spawn"
- `description`: 启动子代理
- `parameters`: {goal, context}
- `execute(goal, context)`: 启动子代理

---

### 12.8 `agent/tools/cron.py`

**功能**: 定时任务工具。

#### `CronTool` 类

**方法**:
- `name`: "cron"
- `description`: 调度提醒和任务
- `parameters`: {action, message, every_seconds, cron_expr, tz, at, job_id}
- `execute(action, ...)`: 执行操作

**支持的 action**:
- `add`: 添加任务
- `list`: 列出任务
- `remove`: 删除任务

**上下文管理**:
- `set_context(channel, chat_id)`: 设置上下文
- `set_cron_context(active)`: 设置 cron 执行上下文
- `reset_cron_context(token)`: 恢复上下文

**特性**: 防止在 cron job 内部递归添加任务

---

### 12.9 `agent/tools/mcp.py`

**功能**: MCP (Model Context Protocol) 集成。

#### `MCPToolWrapper` 类

**功能**: 包装 MCP 服务器工具为 nanobot Tool。

---

#### `connect_mcp_servers()`
**签名**: `async def connect_mcp_servers(config: dict, registry: ToolRegistry)`

**功能**: 连接 MCP 服务器。

**参数**:
- `config`: MCP 配置
- `registry`: 工具注册表

**支持的传输**: stdio, SSE, streamableHttp

---

---

## 13. 数据流转示例

### 完整实例：Telegram 用户发送消息 "/remind me to buy milk in 10 minutes"

**步骤 1: 用户发送消息**
```
Telegram 用户 → Telegram Bot API
```

**步骤 2: Telegram Channel 接收**
```python
# channels/telegram.py
async def poll():
    update = await bot.get_updates()
    msg = InboundMessage(
        channel="telegram",
        sender_id=str(update.from_user.id),
        chat_id=str(update.chat.id),
        content=update.text
    )
    await bus.publish_inbound(msg)
```

**步骤 3: 消息总线传递**
```python
# bus/queue.py
await self._inbound_queue.put(msg)
```

**步骤 4: AgentLoop 接收消息**
```python
# agent/loop.py
async def run():
    while True:
        msg = await self.bus.get_inbound()
        await self._process_message(msg)
```

**步骤 5: 获取会话**
```python
# session/manager.py
session = self.session_manager.get_or_create(f"telegram:{chat_id}")
```

**步骤 6: 构建上下文**
```python
# agent/context.py
system_prompt = await build_system_prompt(workspace, None)
messages = build_messages(system_prompt, session, msg)
# messages = [
#     {"role": "system", "content": "..."},
#     {"role": "user", "content": "/remind me to buy milk in 10 minutes"}
# ]
```

**步骤 7: 调用 LLM**
```python
# providers/litellm_provider.py
response = await provider.chat_with_retry(
    messages=messages,
    tools=registry.get_definitions()
)
# response.tool_calls = [ToolCall(name="cron", args={"action": "add", ...})]
```

**步骤 8: 执行工具**
```python
# agent/tools/registry.py
result = await registry.execute("cron", {"action": "add", ...})

# agent/tools/cron.py
job = self._cron.add_job(
    name="remind to buy milk",
    schedule=CronSchedule(kind="every", every_ms=600000),
    message="buy milk",
    deliver=True,
    channel="telegram",
    to=chat_id
)
```

**步骤 9: 保存会话**
```python
# session/manager.py
session.messages.append({"role": "user", "content": "..."})
session.messages.append({"role": "assistant", "tool_calls": [...]})
session.messages.append({"role": "tool", "content": "Created job..."})
self.session_manager.save(session)
```

**步骤 10: 发送回复**
```python
# agent/tools/message.py
await bus.publish_outbound(OutboundMessage(
    channel="telegram",
    chat_id=chat_id,
    content="Created job 'remind to buy milk' (id: abc123)"
))

# channels/manager.py
await telegram_channel.send(msg)

# Telegram Bot API → 用户
```

---

## 14. 总结

nanobot 是一个设计精良的轻量级 AI 助手框架，核心特点：

1. **简洁架构** - 消息队列解耦，模块化设计
2. **高度可扩展** - 插件式 Channel、动态技能、MCP 工具
3. **多 Provider 支持** - 20+ LLM 提供商，自动匹配
4. **智能记忆** - 自动压缩，长期 + 短期双层存储
5. **跨平台** - Windows/Linux/macOS 全支持

### 核心文件数量统计

| 模块 | 文件数 | 主要类数 |
|------|--------|----------|
| CLI | 1 | 1 (Typer app) |
| Agent | 5 | 4 (AgentLoop, ContextBuilder, MemoryConsolidator, SkillManager, SubagentTask) |
| Tools | 9 | 12+ (各工具类) |
| Bus | 2 | 3 (MessageBus, InboundMessage, OutboundMessage) |
| Channels | 5+ | 6+ (BaseChannel, ChannelManager, 各 Channel 实现) |
| Providers | 6 | 7 (LLMProvider, LiteLLMProvider, CustomProvider, AzureOpenAIProvider, OpenAICodexProvider, GroqTranscriptionProvider) |
| Session | 1 | 2 (Session, SessionManager) |
| Config | 3 | 3 (Config, ProvidersConfig) |
| Cron | 2 | 6 (CronSchedule, CronPayload, CronJob, CronJobState, CronStore, CronService) |
| Heartbeat | 1 | 1 (HeartbeatService) |
| Utils | 2 | 2 (辅助函数) |

**总计**: 约 37 个核心文件，40+ 个核心类，100+ 个方法。
