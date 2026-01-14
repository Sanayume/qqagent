# LangGraph QQ Agent

> 一个基于 **Python** + **LangGraph** + **NapCat (OneBot11)** + **MCP** 构建的现代化智能 QQ 机器人。

本项目旨在构建一个高度可扩展、具备复杂推理能力和工具使用能力的 Agent，而非简单的对话机器人。它利用 LangGraph 的图编排能力管理对话状态，通过 MCP 协议无限扩展外部工具库。

## 🛠️ 核心实现逻辑

本项目基于以下核心技术栈构建，实现了一套完整的 Agentic Workflow：

1.  **事件驱动层 (OneBot Adapter)**
    -   使用 **NapCat** 作为 QQ 客户端，通过 OneBot11 协议（Reverse WebSocket）与后端通信。
    -   `src/adapters/onebot.py` 负责将 QQ 事件（消息、通知）转换为标准的 Python 对象，并将 Agent 的回复转换为 OneBot 消息段（支持文本、图片、引用、转发）。

2.  **认知引擎 (LangGraph Agent)**
    -   核心逻辑基于 **LangGraph** 构建的状态图 (`src/agent/graph.py`)。
    -   **ReAct 架构**：Agent 接收消息 -> 思考 (LLM) -> 决定行动 (Call Tool) -> 执行工具 -> 观察结果 -> 再思考 -> 生成最终回复。
    -   支持 **Thinking Models** (如 Gemini 2.5, Claude 3.5)，能够处理复杂的推理任务。

3.  **工具协议 (MCP - Model Context Protocol)**
    -   **首创性集成**：通过 MCP 协议 (`src/adapters/mcp.py`) 连接外部工具服务器。
    -   这意味着你的 Bot 可以轻松拥有联网搜索 (Tavily)、读写知识库 (RAG)、操作文件系统、管理记忆图谱 (Memory Graph) 等能力，而无需修改核心代码。
    -   配置在 `config/mcp_servers.json` 中定义，支持 stdio 和 sse 传输。

4.  **状态与记忆 (State & Memory)**
    -   **长期记忆**：使用 SQLite (`data/sessions.db`) 持久化保存所有会话历史。
    -   **会话管理**：支持灵活的上下文隔离策略（全局共享/群内隔离/用户隔离），在 `src/session/manager.py` 中实现。

## 🚀 快速开始 (Quick Start)

只需几步即可启动你的 Agent。

### 1. 环境准备

确保安装了 Python 3.11+ 和 Conda。

```bash
# 创建并激活环境
conda create -n qqagent python=3.11 -y
conda activate qqagent

# 安装项目依赖
pip install -e .
```

### 2. 配置文件

复制示例配置并填入你的 API Key。

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# LLM API 配置 (支持 OpenAI 兼容接口)
OPENAI_API_KEY=sk-xxxx
OPENAI_API_BASE=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini  # 或 gemini-2.5-flash

# OneBot 配置 (默认反向 WS)
ONEBOT_MODE=reverse
ONEBOT_REVERSE_WS_PORT=5140
ONEBOT_TOKEN=your_token    # 可选
```

### 3. 配置 NapCat (QQ 客户端)

1.  启动 NapCat (推荐使用 Docker 或 Windows 客户端)。
2.  进入 NapCat WebUI -> 网络配置 -> **WebSocket 客户端**。
3.  添加配置：
    -   **URL**: `ws://127.0.0.1:5140/onebot`
    -   **Token**: (留空或填写 .env 中的值)
    -   **启用**: 开启

### 4. 启动 Agent

```bash
# 启动主程序
python -m src.main
```

看到 `Reverse WS server listening on 127.0.0.1:5140` 即表示启动成功。当 NapCat 连接上来时，控制台会显示 `Bot connected!`。

---

## ✨ 功能特性

-   **多模态交互**：不仅支持文字，还能完美处理图片收发、引用回复、合并转发。
-   **角色扮演预设**：支持热重载的角色预设 (`config/presets/*.yaml`)，可定制 system prompt 和说话风格（内置猫娘、琪露诺等预设）。
-   **沙盒测试模式**：运行 `python -m src.sandbox` 可在终端直接模拟对话，无需登 QQ。
-   **LangSmith 可视化**：配置 LangSmith Key 后，可在网页端查看 Agent 的完整思考链和工具调用过程，方便调试。

## 📂 项目结构

```
qqagent/
├── config/                 # 配置文件
│   ├── mcp_servers.json    # MCP 工具服务器配置
│   └── presets/            # 角色预设 (YAML)
├── src/
│   ├── adapters/           # 协议适配 (OneBot, MCP)
│   ├── agent/              # LangGraph 核心图定义
│   ├── core/               # 基础数据结构
│   ├── memory/             # 数据库存储
│   └── main.py             # 入口文件
├── data/                   # 数据存储 (SQLite)
├── .env                    # 敏感配置
└── config.yaml             # 业务配置
```

## 🔧 MCP 工具配置

本项目的一大特色是支持 MCP。你可以在 `config/mcp_servers.json` 中添加任何符合 MCP 标准的服务器。

示例：添加一个 Web 搜索服务

```json
{
  "mcpServers": {
    "tavily-search": {
      "command": "npx",
      "args": ["-y", "@tavily/mcp-server-tavily-search"],
      "env": {
        "TAVILY_API_KEY": "tvly-xxxx"
      }
    }
  }
}
```

## 📄 License

MIT
