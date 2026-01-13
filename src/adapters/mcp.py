"""
MCP (Model Context Protocol) 客户端管理器

负责：
- 加载 MCP 服务器配置
- 启动/停止 MCP 服务器进程
- 获取 MCP 工具供 Agent 使用
- 追踪各服务器加载状态
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.logger import log


@dataclass
class MCPServerStatus:
    """MCP 服务器状态"""
    name: str
    command: str
    status: str = "pending"  # pending, loading, success, failed
    error: str | None = None
    tools: list[str] = field(default_factory=list)


class MCPManager:
    """MCP 服务器管理器

    管理多个 MCP 服务器的生命周期，并将它们的工具暴露给 Agent。
    配置格式与 Claude Desktop 一致。
    """

    def __init__(
        self,
        config_path: str = "config/mcp_servers.json",
        timeout: float = 60.0,
        retry_count: int = 2,
    ):
        """初始化 MCP 管理器

        Args:
            config_path: MCP 服务器配置文件路径 (JSON)
            timeout: 启动超时时间 (秒)，默认 60 秒
            retry_count: 失败重试次数，默认 2 次
        """
        self.config_path = Path(config_path)
        self.timeout = timeout
        self.retry_count = retry_count
        self._client = None
        self._tools: list = []
        self._started = False
        self._server_status: dict[str, MCPServerStatus] = {}
        self._tool_source: dict[str, str] = {}  # tool_name -> server_name

    def _load_config(self) -> dict[str, Any]:
        """加载配置文件"""
        if not self.config_path.exists():
            log.debug(f"MCP config not found: {self.config_path}")
            return {"mcpServers": {}}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config
        except json.JSONDecodeError as e:
            log.error(f"Invalid MCP config JSON: {e}")
            return {"mcpServers": {}}
        except Exception as e:
            log.error(f"Failed to load MCP config: {e}")
            return {"mcpServers": {}}

    def _convert_config_format(self, config: dict) -> dict:
        """将 Claude Desktop 格式转换为 langchain-mcp-adapters 格式

        Claude Desktop 格式:
        {
            "mcpServers": {
                "server-name": {
                    "command": "...",
                    "args": [...],
                    "env": {...},
                    "cwd": "..."  (可选)
                }
            }
        }

        langchain-mcp-adapters 格式:
        {
            "server-name": {
                "command": "...",
                "args": [...],
                "env": {...},
                "cwd": "...",
                "transport": "stdio"
            }
        }
        """
        mcp_servers = config.get("mcpServers", {})
        result = {}

        for name, server_config in mcp_servers.items():
            converted = {
                "command": server_config.get("command", ""),
                "args": server_config.get("args", []),
                "transport": "stdio",  # 默认使用 stdio 传输
            }

            # 可选参数
            if "env" in server_config:
                converted["env"] = server_config["env"]
            if "cwd" in server_config:
                converted["cwd"] = server_config["cwd"]
            if "encoding" in server_config:
                converted["encoding"] = server_config["encoding"]

            result[name] = converted

        return result

    async def start(self) -> bool:
        """启动所有 MCP 服务器并获取工具

        Returns:
            是否成功启动 (无服务器配置时也返回 True)
        """
        if self._started:
            log.warning("MCP Manager already started")
            return True

        config = self._load_config()
        servers = config.get("mcpServers", {})

        if not servers:
            log.info("No MCP servers configured, skipping MCP initialization")
            self._started = True
            return True

        # 初始化服务器状态
        for name, server_config in servers.items():
            self._server_status[name] = MCPServerStatus(
                name=name,
                command=server_config.get("command", "unknown"),
                status="pending"
            )

        try:
            await self._do_start(config)
            # _do_start 现在会逐个处理服务器，不会抛出异常
            # 只有全部失败时返回 False
            success_count = sum(1 for s in self._server_status.values() if s.status == "success")
            return success_count > 0
            
        except ImportError as e:
            # ImportError 不重试 - 缺少 langchain-mcp-adapters
            log.warning("langchain-mcp-adapters not installed, MCP disabled")
            log.warning("Install with: pip install langchain-mcp-adapters")
            for name in self._server_status:
                self._server_status[name].status = "failed"
                self._server_status[name].error = "langchain-mcp-adapters not installed"
            self._started = True
            return False

    def _extract_error_details(self, e: BaseException) -> str:
        """从 ExceptionGroup/TaskGroup 中提取详细错误信息"""
        errors = []

        # Python 3.11+ ExceptionGroup
        if hasattr(e, "exceptions"):
            for sub_exc in e.exceptions:
                # 递归提取嵌套的 ExceptionGroup
                if hasattr(sub_exc, "exceptions"):
                    errors.append(self._extract_error_details(sub_exc))
                else:
                    errors.append(f"{type(sub_exc).__name__}: {sub_exc}")
        else:
            errors.append(f"{type(e).__name__}: {e}")

        return "; ".join(errors) if errors else str(e)

    async def _do_start(self, config: dict):
        """实际执行启动逻辑 - 逐个服务器启动，容错处理"""
        from langchain_mcp_adapters.client import MultiServerMCPClient

        converted_config = self._convert_config_format(config)
        log.info(f"Starting MCP servers: {list(converted_config.keys())} (timeout={self.timeout}s)")

        # 打印详细配置用于调试
        for name, cfg in converted_config.items():
            log.debug(f"  [{name}] command={cfg.get('command')} args={cfg.get('args')} cwd={cfg.get('cwd', 'N/A')}")

        # 标记所有服务器为 loading
        for name in self._server_status:
            self._server_status[name].status = "loading"

        # 逐个启动服务器，容错处理
        all_tools = []
        successful_servers = []
        
        for server_name, server_config in converted_config.items():
            log.debug(f"Starting server: {server_name}")
            try:
                # 单独为这个服务器创建客户端
                single_config = {server_name: server_config}
                client = MultiServerMCPClient(single_config)
                
                # 设置超时获取工具
                tools = await asyncio.wait_for(
                    client.get_tools(),
                    timeout=min(self.timeout / len(converted_config), 30)  # 每个服务器最多 30 秒
                )
                
                # 成功
                self._server_status[server_name].status = "success"
                self._server_status[server_name].tools = [t.name for t in tools]
                all_tools.extend(tools)
                successful_servers.append(server_name)
                log.info(f"  ✅ [{server_name}] loaded {len(tools)} tools: {[t.name for t in tools]}")
                
            except asyncio.TimeoutError:
                self._server_status[server_name].status = "failed"
                self._server_status[server_name].error = f"启动超时 (>{int(min(self.timeout / len(converted_config), 30))}s)"
                log.warning(f"  ❌ [{server_name}] timeout")
                
            except Exception as e:
                error_msg = self._extract_error_details(e)
                self._server_status[server_name].status = "failed"
                self._server_status[server_name].error = error_msg
                log.warning(f"  ❌ [{server_name}] failed: {error_msg}")

        self._tools = all_tools
        
        # 更新工具来源
        for server_name in successful_servers:
            for tool_name in self._server_status[server_name].tools:
                self._tool_source[tool_name] = server_name

        # 汇总日志
        total = len(converted_config)
        success_count = len(successful_servers)
        if success_count > 0:
            log.success(f"MCP loaded {len(all_tools)} tools from {success_count}/{total} servers")
        else:
            log.warning(f"MCP: all {total} servers failed to start")
        
        self._started = True

    def _identify_tool_sources(self):
        """尝试识别工具来源

        langchain-mcp-adapters 的工具通常带有服务器名前缀或元数据
        """
        server_names = list(self._server_status.keys())

        for tool in self._tools:
            tool_name = getattr(tool, "name", None)
            if not tool_name:
                continue

            source = "unknown"

            # 方法1: 检查工具名是否包含服务器名
            for server in server_names:
                # 将服务器名中的 - 替换为 _ 进行匹配
                normalized_server = server.replace("-", "_")
                if tool_name.startswith(f"{normalized_server}_") or tool_name.startswith(f"{server}_"):
                    source = server
                    break

            # 方法2: 检查工具的 metadata (如果有)
            if source == "unknown" and hasattr(tool, "metadata"):
                metadata = getattr(tool, "metadata", None)
                if metadata and isinstance(metadata, dict) and "server" in metadata:
                    source = metadata["server"]

            # 方法3: 基于已知的工具名模式推断
            if source == "unknown":
                source = self._infer_source_from_tool_name(tool_name, server_names)

            self._tool_source[tool_name] = source

    def _infer_source_from_tool_name(self, tool_name: str, server_names: list[str]) -> str:
        """基于工具名推断来源"""
        # 常见的 MCP 工具名模式
        patterns = {
            "philosophy-rag": ["philosophy_search", "philosophy", "rag_search"],
            "tavily": ["tavily_search", "web_search", "tavily"],
            "memory": ["create_entities", "create_relations", "add_observations",
                      "delete_entities", "delete_observations", "delete_relations",
                      "read_graph", "search_nodes", "open_nodes"],
            "sequential-thinking": ["sequentialthinking"],
            "context7": ["resolve-library-id", "get-library-docs"],
            "serena": ["read_file", "create_text_file", "list_dir", "find_file",
                      "replace_content", "search_for_pattern", "get_symbols",
                      "find_symbol", "execute_shell", "activate_project"],
        }

        for server, keywords in patterns.items():
            if server in server_names:
                for keyword in keywords:
                    if keyword in tool_name.lower() or tool_name.lower().startswith(keyword):
                        return server

        return "unknown"

    async def stop(self):
        """关闭所有 MCP 服务器"""
        if self._client:
            try:
                # 新 API (0.1.0+): 尝试调用 close/disconnect 方法
                if hasattr(self._client, "close"):
                    await self._client.close()
                elif hasattr(self._client, "disconnect"):
                    await self._client.disconnect()
                # 如果没有显式关闭方法，client 会在垃圾回收时清理
                log.info("MCP servers stopped")
            except Exception as e:
                log.error(f"Error stopping MCP servers: {e}")
            finally:
                self._client = None
                self._tools = []
                self._started = False

    def get_tools(self) -> list:
        """获取所有 MCP 工具

        Returns:
            MCP 工具列表 (如果未启动或无工具则返回空列表)
        """
        return self._tools

    def is_started(self) -> bool:
        """检查是否已启动"""
        return self._started

    @property
    def tool_count(self) -> int:
        """获取工具数量"""
        return len(self._tools)

    @property
    def server_names(self) -> list[str]:
        """获取配置的服务器名称列表"""
        config = self._load_config()
        return list(config.get("mcpServers", {}).keys())

    def get_server_status(self) -> dict[str, MCPServerStatus]:
        """获取所有服务器的状态"""
        return self._server_status.copy()

    def get_tool_source(self, tool_name: str) -> str:
        """获取工具的来源服务器"""
        return self._tool_source.get(tool_name, "unknown")

    def get_status_report(self) -> str:
        """生成详细的状态报告"""
        lines = ["MCP 服务器状态报告", "=" * 40]

        if not self._server_status:
            lines.append("未配置任何 MCP 服务器")
            return "\n".join(lines)

        # 统计
        total = len(self._server_status)
        success = sum(1 for s in self._server_status.values() if s.status == "success")
        failed = sum(1 for s in self._server_status.values() if s.status == "failed")

        lines.append(f"服务器: {success}/{total} 成功, {failed} 失败")
        lines.append(f"总工具数: {len(self._tools)}")
        lines.append("")

        # 各服务器详情
        for name, status in self._server_status.items():
            icon = "✅" if status.status == "success" else "❌" if status.status == "failed" else "⏳"
            lines.append(f"{icon} {name}")
            lines.append(f"   命令: {status.command}")
            lines.append(f"   状态: {status.status}")

            if status.error:
                lines.append(f"   错误: {status.error}")

            if status.tools:
                lines.append(f"   工具 ({len(status.tools)}): {', '.join(status.tools)}")
            elif status.status == "success":
                # 服务器成功但无工具被归属
                unknown_tools = [t for t, s in self._tool_source.items() if s == "unknown"]
                if unknown_tools:
                    lines.append(f"   工具: (可能包含: {', '.join(unknown_tools[:3])}...)")

            lines.append("")

        # 工具来源汇总
        if self._tools:
            lines.append("工具来源映射:")
            by_source: dict[str, list[str]] = {}
            for tool_name, source in self._tool_source.items():
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(tool_name)

            for source, tools in sorted(by_source.items()):
                lines.append(f"  [{source}] {', '.join(tools)}")

        return "\n".join(lines)
