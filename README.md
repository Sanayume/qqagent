# LangGraph QQ Agent

> 基于 Python + LangGraph + NapCat + MCP 构建的 QQ 机器人

## 特性

- **LangGraph ReAct Agent** - 基于 LangGraph 的 ReAct 架构，支持工具调用和多轮对话
- **MCP 工具协议** - 支持 MCP (Model Context Protocol) 标准，可扩展外部工具服务器
- **双模式 WebSocket** - 支持正向和反向 WebSocket 连接 NapCat
- **预设系统** - 灵活的角色预设，支持热重载
- **SQLite 会话存储** - 持久化会话历史，支持多种会话隔离模式
- **沙盒测试模式** - 无需启动 QQ Bot 即可测试 Agent 功能
- **LangSmith 追踪** - 完整的调试和监控链路

## 项目结构

```
qqagent/
├── pyproject.toml              # Python 项目配置
├── config.yaml                 # 业务配置 (热重载)
├── .env                        # 环境变量配置
│
├── src/
│   ├── main.py                 # QQ Bot 主程序入口
│   ├── sandbox.py              # 沙盒测试模式 (CLI)
│   │
│   ├── adapters/
│   │   ├── onebot.py           # OneBot11 WebSocket 适配器
│   │   └── mcp.py              # MCP 客户端管理器
│   │
│   ├── agent/
│   │   ├── graph.py            # LangGraph Agent 定义
│   │   ├── state.py            # Agent 状态类型定义
│   │   └── tools.py            # 内置工具 (时间、计算)
│   │
│   ├── memory/
│   │   └── store.py            # SQLite 会话存储
│   │
│   ├── presets/
│   │   └── loader.py           # 预设加载器
│   │
│   ├── session/
│   │   └── manager.py          # 会话 ID 管理
│   │
│   └── utils/
│       ├── config.py           # Pydantic 配置模型
│       ├── config_loader.py    # YAML 配置热重载
│       └── logger.py           # Loguru 日志
│
├── config/
│   ├── mcp_servers.json        # MCP 服务器配置
│   └── presets/                # 角色预设文件
│       ├── default.yaml
│       ├── catgirl.yaml
│       └── ...
│
├── mcpserver/                  # 自定义 MCP 服务器
│   └── mcp_rag_server/         # 哲学知识库 RAG 服务器
│
└── data/
    └── sessions.db             # SQLite 会话数据库
```

## 快速开始

### 1. 创建环境

```bash
conda create -n qqagent python=3.11 -y
conda activate qqagent
```

### 2. 安装依赖

```bash
pip install -e .
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并修改：

```env
# OneBot 配置
ONEBOT_MODE=reverse
ONEBOT_REVERSE_WS_HOST=127.0.0.1
ONEBOT_REVERSE_WS_PORT=5140
ONEBOT_REVERSE_WS_PATH=/onebot
ONEBOT_TOKEN=your_token

# LLM 配置
OPENAI_API_KEY=your_key
OPENAI_API_BASE=https://api.openai.com/v1  # 或代理地址
DEFAULT_MODEL=gpt-4o-mini

# LangSmith (可选)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=langgraph-qq-agent
```

### 4. NapCat 配置

在 NapCat WebUI 中配置 WebSocket Client：

| 配置项 | 值 |
|--------|-----|
| URL | `ws://127.0.0.1:5140/onebot` |
| Token | 与 `.env` 中 `ONEBOT_TOKEN` 一致 |
| 消息格式 | Array |

### 5. 运行

```bash
# 运行 QQ Bot
python -m src.main

# 或沙盒测试模式 (无需 NapCat)
python -m src.sandbox
```

## 沙盒模式

沙盒模式提供命令行聊天界面，用于测试 Agent 功能：

```bash
python -m src.sandbox
```

**可用命令：**

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/clear` | 清除当前会话历史 |
| `/tools` | 查看可用工具 |
| `/mcp` | 查看 MCP 服务器状态 |
| `/presets` | 列出所有预设 |
| `/preset <name>` | 切换预设 |
| `/reload` | 热重载 Agent |
| `/quit` | 退出 |

## MCP 工具配置

在 `config/mcp_servers.json` 中配置 MCP 服务器：

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/server"
    },
    "npx-server": {
      "command": "npx",
      "args": ["-y", "@some/mcp-server"],
      "env": {
        "API_KEY": "xxx"
      }
    }
  }
}
```

支持的配置项：
- `command`: 可执行命令
- `args`: 命令参数
- `cwd`: 工作目录
- `env`: 环境变量

## 预设系统

预设文件放在 `config/presets/` 目录下：

```yaml
# config/presets/catgirl.yaml
name: 猫娘
description: 可爱的猫娘助手

keywords:
  - 猫娘
  - 喵

system_prompt: |
  你是一只可爱的猫娘助手喵~
  说话特点：
  - 句尾加"喵"或"喵~"
  - 用可爱的语气说话

input_template: "{message}"
```

## 内置工具

| 工具名 | 说明 |
|--------|------|
| `get_current_time` | 获取当前时间 |
| `get_current_date` | 获取今天日期和星期 |
| `calculate` | 安全的数学表达式计算 |

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        QQ Agent                              │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   OneBot     │    │  LangGraph   │    │    MCP       │  │
│  │   Adapter    │───▶│    Agent     │◀───│   Manager    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   │                    │          │
│         ▼                   ▼                    ▼          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   NapCat     │    │   LLM API    │    │  MCP Server  │  │
│  │  (QQ客户端)   │    │ (OpenAI等)   │    │  (外部工具)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Memory     │    │   Presets    │    │   Session    │  │
│  │   Store      │    │   Manager    │    │   Manager    │  │
│  │  (SQLite)    │    │   (YAML)     │    │              │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 会话管理

支持多种会话隔离模式，在 `config.yaml` 中配置：

```yaml
session:
  # 全局用户: 这些用户在所有群/私聊共享一个上下文
  global_users: [12345678]

  # 用户隔离群: 这些群内每个用户独立上下文
  per_user_groups: [11223344]

  # 所有群开启用户隔离
  all_groups_per_user: false
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check src/
```

## 已知限制

- **代理兼容性**: 某些 OpenAI 兼容代理在处理工具调用结果时可能出错 (400 INVALID_ARGUMENT)
- **并行工具调用**: 已禁用并行工具调用以兼容更多代理

## License

MIT
