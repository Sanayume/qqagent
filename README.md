# LangGraph QQ Agent

> 一个基于 **Python** + **LangGraph** + **NapCat (OneBot11)** + **MCP** 构建的现代化智能 QQ 机器人。

本项目旨在构建一个高度可扩展、具备复杂推理能力和工具使用能力的 Agent，而非简单的对话机器人。它利用 LangGraph 的图编排能力管理对话状态，通过 MCP 协议无限扩展外部工具库。

## ✨ 核心特性

- **🤖 ReAct Agent 架构**：思考→行动→观察，支持多轮工具调用
- **🖼️ 多模态交互**：完美处理图片收发、引用回复、合并转发
- **🔧 MCP 工具集成**：通过 Model Context Protocol 无限扩展能力
- **💾 会话持久化**：SQLite 存储，重启不丢失对话历史
- **🎭 角色预设**：支持热重载的 YAML 预设文件
- **📊 群消息聚合**：智能聚合连续群消息，减少 API 调用
- **🔄 配置热重载**：修改 `.env` 或 `config.yaml` 自动生效

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 创建并激活环境 (Python 3.11+)
conda create -n qqagent python=3.11 -y
conda activate qqagent

# 安装项目依赖
pip install -e .
```

### 2. 配置文件

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# ===== LLM 配置 =====
OPENAI_API_KEY=sk-xxxx
OPENAI_API_BASE=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini

# ===== OneBot 配置 =====
ONEBOT_MODE=reverse                    # reverse/forward/both
ONEBOT_REVERSE_WS_PORT=5140
ONEBOT_TOKEN=                          # 可选

# ===== Agent 行为 =====
AGENT_DEFAULT_PRESET=琪露诺            # 默认角色预设
AGENT_ALLOW_AT_REPLY=true              # 响应 @
AGENT_ALLOW_PRIVATE=true               # 响应私聊
AGENT_ALLOW_ALL_GROUP_MSG=false        # 响应所有群消息（无需@）
AGENT_SILENT_ERRORS=false              # 出错时静默（不发送错误提示）
AGENT_MAX_HISTORY_MESSAGES=70          # 历史消息保留数量

# ===== 会话管理 =====
AGENT_SESSION_GLOBAL_USERS=[]          # 全局用户 (共享上下文)
AGENT_SESSION_PER_USER_GROUPS=[]       # 用户隔离的群列表
AGENT_SESSION_ALL_GROUPS_PER_USER=false

# ===== LangSmith 调试 (可选) =====
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_xxx
LANGCHAIN_PROJECT=langgraph-qq-agent
```

### 3. 配置 NapCat

1. 启动 NapCat (推荐 Docker 或 Windows 客户端)
2. WebUI → 网络配置 → **WebSocket 客户端**
3. 添加 URL: `ws://127.0.0.1:5140/onebot`

### 4. 启动

```bash
python -m src.main
```

看到 `Bot connected!` 即表示成功连接。

---

## 🛠️ 核心架构

```
┌─────────────────────────────────────────────────────┐
│ OneBot Adapter (WebSocket)                          │
│   ↓ 消息事件                                        │
├─────────────────────────────────────────────────────┤
│ Message Aggregator (群消息聚合)                      │
│   ↓ 聚合后的消息                                    │
├─────────────────────────────────────────────────────┤
│ LangGraph Agent (ReAct 循环)                        │
│   ├── LLM (思考)                                    │
│   ├── Tools (行动)                                  │
│   └── Memory (记忆)                                 │
├─────────────────────────────────────────────────────┤
│ MCP Tool Servers (外部工具)                         │
└─────────────────────────────────────────────────────┘
```

**数据流**：
1. QQ 消息 → OneBot 适配器解析
2. 图片下载、引用获取、转发内容提取
3. 构建多模态 LangChain 消息
4. Agent 循环处理（可能多轮工具调用）
5. 通过 `send_message` 工具发送回复
6. 历史存入 SQLite

---

## 📂 项目结构

```
qqagent/
├── config/
│   ├── mcp_servers.json        # MCP 工具服务器配置
│   └── presets/                # 角色预设 (YAML)
│       ├── default.yaml
│       └── 琪露诺.yaml
├── src/
│   ├── adapters/               # 协议适配
│   │   ├── onebot.py           # OneBot WebSocket
│   │   └── mcp.py              # MCP 客户端
│   ├── agent/                  # Agent 核心
│   │   ├── graph.py            # LangGraph 定义
│   │   ├── state.py            # 状态类型
│   │   └── tools.py            # 内置工具
│   ├── core/                   # 底层工具函数
│   │   ├── onebot.py           # 消息解析/构建
│   │   ├── media.py            # 图片下载/编码
│   │   └── llm_message.py      # LangChain 消息
│   ├── memory/                 # 存储
│   │   └── store.py            # SQLite 持久化
│   ├── session/                # 会话管理
│   │   ├── manager.py          # Session ID 策略
│   │   └── aggregator.py       # 群消息聚合
│   ├── presets/                # 预设加载
│   ├── utils/                  # 工具模块
│   └── main.py                 # 入口
├── data/
│   └── sessions.db             # SQLite 数据库
└── .env                        # 敏感配置
```

---

## 🔧 MCP 工具配置

在 `config/mcp_servers.json` 中添加 MCP 服务器：

```json
{
  "mcpServers": {
    "tavily-search": {
      "command": "npx",
      "args": ["-y", "@tavily/mcp-server-tavily-search"],
      "env": {
        "TAVILY_API_KEY": "tvly-xxxx"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-filesystem", "/path/to/dir"]
    }
  }
}
```

---

## 🎭 角色预设

在 `config/presets/` 创建 YAML 文件：

```yaml
name: 猫娘
system_prompt: |
  你是一只可爱的猫娘，说话带「喵」。
  你会卖萌，喜欢被摸头。
keywords:
  - 猫娘
  - 喵
```

通过 `AGENT_DEFAULT_PRESET=猫娘` 启用。

---

## 🧪 沙盒测试

无需 QQ，直接在终端测试：

```bash
# CLI 模式
python -m src.sandbox

# Web 模式 (带 UI)
python -m src.sandbox_web
```

---

## 📄 License

MIT
