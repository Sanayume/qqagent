"""
沙盒模式 - 命令行聊天测试界面

在不启动 QQ Bot 的情况下测试 Agent 功能：
- 对话
- 工具调用
- 会话历史
- 预设系统
- 代码热重载监控

用法: python -m src.sandbox
"""

import asyncio
import importlib
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from src.adapters.mcp import MCPManager
from src.agent.graph import QQAgent
from src.agent.tools import DEFAULT_TOOLS
from src.memory import MemoryStore
from src.presets import PresetManager
from src.utils.config import load_settings
from src.utils.config_loader import get_config_loader
from src.utils.logger import setup_logger, log


# 加载 .env 文件
load_dotenv()


class CodeChangeHandler(FileSystemEventHandler):
    """监控代码文件变化"""

    def __init__(self):
        self.last_change = None
        self.changed_files = []

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and event.src_path.endswith(".py"):
            # 忽略 __pycache__
            if "__pycache__" in event.src_path:
                return

            self.last_change = datetime.now()
            rel_path = os.path.relpath(event.src_path)
            if rel_path not in self.changed_files:
                self.changed_files.append(rel_path)
            print(f"\n📝 代码变更: {rel_path}")
            print("   输入 /reload 重新加载 Agent")
            print("你: ", end="", flush=True)

    def get_changes(self) -> list[str]:
        """获取并清空变更列表"""
        changes = self.changed_files.copy()
        self.changed_files.clear()
        return changes


async def create_agent(settings, config_loader, memory_store, mcp_manager):
    """创建 Agent 实例 (用于初始化和重载)"""
    # 重新加载模块
    import src.agent.tools
    import src.agent.graph
    import src.presets.loader

    importlib.reload(src.agent.tools)
    importlib.reload(src.agent.graph)
    importlib.reload(src.presets.loader)

    # 重新导入
    from src.agent.tools import DEFAULT_TOOLS
    from src.agent.graph import QQAgent
    from src.presets import PresetManager

    # PresetManager
    preset_manager = PresetManager(
        config_loader=config_loader,
        preset_dir="config/presets",
    )
    default_preset = preset_manager.get_default()

    # MCP 工具
    mcp_tools = mcp_manager.get_tools()

    # 合并工具
    all_tools = DEFAULT_TOOLS + mcp_tools

    # 创建 Agent
    agent = QQAgent(
        model=settings.llm.default_model,
        api_key=settings.llm.openai_api_key,
        base_url=settings.llm.openai_api_base,
        default_system_prompt=default_preset.system_prompt,
        memory_store=memory_store,
        tools=all_tools,
    )

    return agent, all_tools, default_preset, preset_manager


async def main():
    # 设置日志 (DEBUG 级别，查看详细信息)
    setup_logger(level="DEBUG")

    print("=" * 60)
    print("  LangGraph QQ Agent - 沙盒测试模式")
    print("=" * 60)
    print()

    # 加载配置
    settings = load_settings()
    config_loader = get_config_loader()

    print(f"LLM Model: {settings.llm.default_model}")
    print(f"API Base: {settings.llm.openai_api_base or 'default'}")

    # 设置 LangSmith
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
        print(f"LangSmith: Enabled ({settings.langchain_project})")
    else:
        print("LangSmith: Disabled")

    # 初始化组件
    print("\n初始化组件...")

    # MemoryStore
    memory_store = MemoryStore(db_path="data/sandbox_sessions.db", max_messages=20)
    print(f"  MemoryStore: OK ({memory_store.get_session_count()} sessions)")

    # MCP (超时 120 秒，重试 2 次)
    mcp_manager = MCPManager("config/mcp_servers.json", timeout=120.0, retry_count=2)
    print("  MCP: 正在启动服务器 (最长等待 120 秒)...")
    await mcp_manager.start()
    mcp_tools = mcp_manager.get_tools()
    print(f"  MCP: OK ({len(mcp_tools)} tools from {len(mcp_manager.server_names)} servers)")

    # 创建 Agent
    agent, all_tools, current_preset, preset_manager = await create_agent(
        settings, config_loader, memory_store, mcp_manager
    )
    print(f"  Presets: {preset_manager.list_all()}")
    print(f"  Tools: {[t.name for t in all_tools]}")
    print("  Agent: OK")

    # 启动代码监控
    code_handler = CodeChangeHandler()
    observer = Observer()
    observer.schedule(code_handler, "src", recursive=True)
    observer.start()
    print("  热重载监控: OK (监控 src/ 目录)")

    # 会话配置
    session_id = "sandbox_test"
    user_id = 10000
    user_name = "测试用户"

    print()
    print("=" * 60)
    print("  开始聊天 (输入 /help 查看命令)")
    print("=" * 60)
    print()

    try:
        while True:
            try:
                # 获取用户输入
                user_input = input("你: ").strip()

                if not user_input:
                    continue

                # 处理命令
                if user_input.startswith("/"):
                    # 分离命令和参数
                    parts = user_input.split(maxsplit=1)
                    cmd = parts[0].lower()
                    cmd_arg = parts[1] if len(parts) > 1 else ""

                    if cmd == "/help":
                        print("""
命令列表:
  /help          - 显示帮助
  /clear         - 清除当前会话历史
  /sessions      - 查看所有会话
  /tools         - 查看可用工具 (显示来源)
  /mcp           - 查看 MCP 服务器详细状态
  /presets       - 列出所有预设
  /preset        - 查看当前预设
  /preset <name> - 切换到指定预设
  /reload        - 重新加载 Agent (热重载)
  /quit          - 退出
""")
                        continue

                    elif cmd == "/clear":
                        agent.clear_session(session_id)
                        print("会话历史已清除\n")
                        continue

                    elif cmd == "/sessions":
                        sessions = memory_store.get_all_session_ids()
                        print(f"会话列表: {sessions}\n")
                        continue

                    elif cmd == "/tools":
                        print("可用工具:")
                        for tool in all_tools:
                            desc = tool.description.split('\n')[0][:50]
                            source = mcp_manager.get_tool_source(tool.name)
                            source_tag = f" [{source}]" if source != "unknown" else ""
                            print(f"  - {tool.name}{source_tag}: {desc}...")
                        print()
                        continue

                    elif cmd == "/mcp":
                        print()
                        print(mcp_manager.get_status_report())
                        print()
                        continue

                    elif cmd == "/presets":
                        print("可用预设:")
                        for p in preset_manager.list_presets():
                            marker = "* " if p.name == current_preset.name else "  "
                            keywords = f" (关键词: {', '.join(p.keywords)})" if p.keywords else ""
                            print(f"  {marker}{p.name}{keywords}")
                        print()
                        continue

                    elif cmd == "/preset":
                        if cmd_arg:
                            # /preset <name> - 切换预设
                            preset_name = cmd_arg
                            new_preset = preset_manager.get(preset_name)
                            if new_preset:
                                current_preset = new_preset
                                agent.default_system_prompt = current_preset.system_prompt
                                agent.clear_session(session_id)
                                print(f"✅ 已切换到预设: {current_preset.name}")
                                print(f"   (会话历史已清除以应用新预设)")
                            else:
                                print(f"❌ 预设不存在: {preset_name}")
                                print(f"   可用预设: {preset_manager.list_all()}")
                        else:
                            # /preset - 查看当前预设
                            print(f"当前预设: {current_preset.name}")
                            print(f"System prompt:\n{current_preset.system_prompt[:300]}...")
                        print()
                        continue

                    elif cmd == "/reload":
                        changes = code_handler.get_changes()
                        print("🔄 重新加载 Agent...")
                        try:
                            agent, all_tools, current_preset, preset_manager = await create_agent(
                                settings, config_loader, memory_store, mcp_manager
                            )
                            print(f"✅ 重载成功! Tools: {[t.name for t in all_tools]}")
                            if changes:
                                print(f"   已应用变更: {changes}")
                        except Exception as e:
                            print(f"❌ 重载失败: {e}")
                        print()
                        continue

                    elif cmd in ("/quit", "/exit", "/q"):
                        print("再见!")
                        break

                    else:
                        print(f"未知命令: {cmd} (输入 /help 查看帮助)\n")
                        continue

                # 调用 Agent
                print("思考中...")
                chat_response = await agent.chat(
                    message=user_input,
                    session_id=session_id,
                    user_id=user_id,
                    user_name=user_name,
                )

                print(f"\nBot: {chat_response.text}")
                if chat_response.has_images():
                    print(f"[附带 {len(chat_response.images)} 张图片]")
                print()

            except KeyboardInterrupt:
                print("\n\n按 Ctrl+C 退出，或输入 /quit")
                continue

    except KeyboardInterrupt:
        print("\n再见!")

    finally:
        # 清理
        observer.stop()
        observer.join()
        await mcp_manager.stop()
        print("沙盒模式已退出")


if __name__ == "__main__":
    asyncio.run(main())
