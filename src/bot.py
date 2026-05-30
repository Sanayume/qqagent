"""
BotApp - QQ Agent 主应用类

职责：组件生命周期管理、触发检测、消息路由。
处理逻辑已拆分到 src/processing/ 和 src/core/message_fetch。
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path

from src.adapters.onebot import OneBotAdapter, OneBotEvent
from src.adapters.mcp import MCPManager
from src.agent.graph import QQAgent
from src.agent.tool_registry import init_builtin_tools, get_tool_registry
from src.agent.llm import FallbackLLM
from src.memory import MemoryStore
from src.memory.knowledge import KnowledgeStore
from src.presets import PresetManager
from src.utils.config import Settings, load_settings
from src.utils.config_loader import get_config_loader, ConfigLoader
from src.utils.env_loader import get_env_loader
from src.utils.logger import setup_logger, log, log_error

from src.core.onebot import parse_segments, make_text_description, get_file_descriptions
from src.core.stt import get_stt_provider
from src.core.message_fetch import fetch_reply_context, fetch_forward_content
from src.core.context import AppContext, get_app_context
from src.session.aggregator import MessageAggregator, PendingMessage
from src.processing.audio import AudioProcessor
from src.processing.pipeline import MessagePipeline


class BotApp:
    """QQ Agent 主应用类，管理所有组件的生命周期。"""

    def __init__(self):
        self.adapter: OneBotAdapter | None = None
        self.agent: QQAgent | None = None
        self.settings: Settings | None = None
        self.config_loader: ConfigLoader | None = None
        self.memory_store: MemoryStore | None = None
        self.knowledge_store: KnowledgeStore | None = None
        self.mcp_manager: MCPManager | None = None
        self.preset_manager: PresetManager | None = None
        self.group_aggregator: MessageAggregator | None = None
        self.private_aggregator: MessageAggregator | None = None
        self.ctx: AppContext | None = None
        self.audio: AudioProcessor | None = None
        self.pipeline: MessagePipeline | None = None
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._admin_port: int = 8088
        self._tg_adapter = None
        self._runtime_events: dict[str, dict[str, object]] = {
            "env_reload": {"count": 0, "last_at": None, "last_status": "idle", "last_detail": ""},
            "config_reload": {"count": 0, "last_at": None, "last_status": "idle", "last_detail": ""},
        }

        # 触发配置（从 settings 中提取，供 handle_message 使用）
        self.bot_names: list[str] = []
        self.allow_at: bool = True
        self.allow_private: bool = True
        self.allow_all_group: bool = False

    async def start(self):
        """初始化所有组件并启动"""
        self._main_loop = asyncio.get_running_loop()
        env_loader = get_env_loader()
        self._init_config()
        self._init_storage()
        all_tools = await self._init_tools()
        self._init_agent(all_tools)
        env_loader.add_callback(self.on_env_reload)
        self.config_loader.add_callback(self.on_config_reload)
        self._init_adapter()
        self._init_audio_and_context()
        self._init_aggregators()
        self._init_event_handlers()
        await self._start_admin()
        self._log_startup_banner()

        try:
            tasks = [asyncio.create_task(self.adapter.start())]
            tg_task = self._build_telegram_task()
            if tg_task:
                tasks.append(tg_task)
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            log.info("Interrupted by user")
        finally:
            await self.stop()

    def _build_telegram_task(self) -> asyncio.Task | None:
        """若 config.yaml 中启用了 telegram，构建并返回监控协程任务。"""
        tg_cfg = self.config_loader.config._raw.get("telegram", {})
        if not tg_cfg.get("enabled", False):
            return None

        api_id = int(tg_cfg.get("api_id") or os.getenv("TG_API_ID", "0"))
        api_hash = tg_cfg.get("api_hash") or os.getenv("TG_API_HASH", "")
        phone = tg_cfg.get("phone") or os.getenv("TG_PHONE", "")
        session_name = tg_cfg.get("session_name", "tg_session")

        if not api_id or not api_hash:
            log.warning("Telegram 已启用但缺少 api_id/api_hash，跳过启动（请检查 .env 或 config.yaml）")
            return None

        from src.adapters.telegram import TelegramAdapter
        from src.adapters.telegram_monitor import NewsMonitor

        self._tg_adapter = TelegramAdapter(
            api_id=api_id,
            api_hash=api_hash,
            session_path=f"data/{session_name}",
            phone=phone,
        )
        self._news_monitor = NewsMonitor(
            tg_adapter=self._tg_adapter,
            onebot_adapter=self.adapter,
            agent=self.agent,
            monitor_cfg=tg_cfg.get("monitor", {}),
            broadcast_cfg=tg_cfg.get("broadcast", {}),
        )

        log.info("Telegram 监控已启用，随主服务启动")

        async def _run_tg():
            try:
                log.info("Telegram 监控任务启动")
                log.info("正在连接 Telegram...")
                await self._tg_adapter.connect()
                log.info("Telegram 连接完成")
                log.info("正在启动 NewsMonitor...")
                await self._news_monitor.start()
                log.info("NewsMonitor 启动完成")
                log.info("Telegram 进入持续监听")
                await self._tg_adapter.run_forever()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log_error(e, context="Telegram 监控", show_traceback=True)
                log.warning("Telegram 监控任务异常退出；QQ 主服务继续运行")

        return asyncio.create_task(_run_tg())

    def _init_config(self):
        """加载配置和日志"""
        self.settings = load_settings()
        self.config_loader = get_config_loader()
        setup_logger(level=self.settings.log_level)

        log.info("=" * 60)
        log.info("LangGraph QQ Agent Starting...")
        log.info("=" * 60)
        log.info(f"Log Level: {self.settings.log_level}")
        log.info(f"OneBot Mode: {self.settings.onebot.mode}")
        log.info(f"LLM Model: {self.settings.llm.default_model}")
        log.info(f"LangSmith: {'Enabled' if self.settings.langchain_tracing_v2 else 'Disabled'}")

        if self.settings.langchain_api_key:
            os.environ["LANGCHAIN_API_KEY"] = self.settings.langchain_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.settings.langchain_project
            os.environ["LANGCHAIN_TRACING_V2"] = "true" if self.settings.langchain_tracing_v2 else "false"
            log.info(f"LangSmith Project: {self.settings.langchain_project}")

    def _apply_agent_behavior_settings(self):
        """将当前 settings 中的 Agent 行为配置同步到运行时字段。"""
        self.bot_names = self.settings.agent.bot_names
        self.allow_at = self.settings.agent.allow_at_reply
        self.allow_private = self.settings.agent.allow_private
        self.allow_all_group = self.settings.agent.allow_all_group_msg
        log.info(f"Bot names: {self.bot_names}")
        log.info(f"Allow @: {self.allow_at}, Allow private: {self.allow_private}, Allow all group: {self.allow_all_group}")

    def _init_storage(self):
        """初始化存储和预设"""
        self.memory_store = MemoryStore(db_path="data/sessions.db", max_messages=self.settings.agent.max_history_messages)
        log.success(f"MemoryStore initialized: {self.memory_store.get_session_count()} existing sessions")

        self.preset_manager = PresetManager(
            config_loader=self.config_loader,
            preset_dir="config/presets",
        )
        self.knowledge_store = KnowledgeStore(db_path="data/knowledge.db")

    async def _init_tools(self) -> list:
        """启动 MCP 并初始化工具注册表，返回启用的工具列表"""
        self.mcp_manager = MCPManager("config/mcp_servers.json", timeout=120.0, retry_count=2)
        await self.mcp_manager.start()

        init_builtin_tools()
        registry = get_tool_registry()
        for server_name, status in self.mcp_manager.servers.items():
            if status.status == "success":
                server_tools = self.mcp_manager.get_tools_by_server(server_name)
                registry.register_mcp_tools(server_name, server_tools)

        all_tools = registry.get_enabled_tools()
        tool_status = registry.get_status()
        log.info(f"Total tools: {tool_status['total']} (enabled: {tool_status['enabled']}, disabled: {tool_status['disabled']})")
        return all_tools

    def _create_fallback_llm(self, api_key: str = "", base_url: str = "") -> FallbackLLM | None:
        """从 ConfigLoader 构建 FallbackLLM，不满足条件时返回 None"""
        api_key = api_key or self.settings.llm.openai_api_key
        base_url = base_url or self.settings.llm.openai_api_base
        try:
            model_list = self.config_loader.get_fallback_llm_models(
                api_key=api_key,
                base_url=base_url,
                default_model=self.settings.llm.default_model,
            )
            if len(model_list) >= 2:
                log.info(f"FallbackLLM enabled with {len(model_list)} models")
                return FallbackLLM(model_list)
        except Exception as e:
            log.debug(f"FallbackLLM not configured: {e}")
        return None

    def _init_agent(self, all_tools: list):
        """创建 Agent"""
        preset_name = self.settings.agent.default_preset
        default_preset = self.preset_manager.get(preset_name) or self.preset_manager.get_default()
        log.info(f"Default preset: {default_preset.name}")

        fallback_llm = self._create_fallback_llm()
        self.agent = QQAgent(
            model=self.settings.llm.default_model,
            api_key=self.settings.llm.openai_api_key,
            base_url=self.settings.llm.openai_api_base,
            default_system_prompt=default_preset.system_prompt,
            memory_store=self.memory_store,
            knowledge_store=self.knowledge_store,
            fallback_llm=fallback_llm,
            tools=all_tools,
        )
        log.success("Agent created successfully")

    def _init_adapter(self):
        """创建 OneBot 适配器和会话管理器"""
        self.adapter = OneBotAdapter(
            ws_url=self.settings.onebot.ws_url,
            reverse_host=self.settings.onebot.reverse_ws_host,
            reverse_port=self.settings.onebot.reverse_ws_port,
            reverse_path=self.settings.onebot.reverse_ws_path,
            token=self.settings.onebot.token,
            mode=self.settings.onebot.mode,
        )
        from src.session.manager import SessionManager
        self.adapter.session_manager = SessionManager(use_loader=True)
        self._apply_agent_behavior_settings()

    def _refresh_audio_runtime(self):
        """根据当前 settings 重建音频处理器并同步到消息管线。"""
        if not self.adapter:
            return

        stt_provider = get_stt_provider(self.settings.agent.stt_provider)
        self.audio = AudioProcessor(self.adapter, self.settings, stt_provider)
        if self.pipeline:
            self.pipeline.audio = self.audio
        log.info(f"Audio runtime refreshed: mode={self.settings.agent.voice_mode}, stt={self.settings.agent.stt_provider}")

    def _apply_onebot_runtime_settings(self, previous_settings: Settings | None):
        """同步可热更新的 OneBot 配置；需要重启的项给出提示。"""
        if not self.adapter:
            return

        previous = previous_settings.onebot if previous_settings else None
        current = self.settings.onebot

        reconnect_forward = False
        reconnect_reverse = False
        restart_required: list[str] = []

        if previous:
            if previous.ws_url != current.ws_url:
                reconnect_forward = True
            if previous.token != current.token:
                reconnect_forward = True
                reconnect_reverse = True
            if previous.mode != current.mode:
                restart_required.append("mode")
            if previous.reverse_ws_host != current.reverse_ws_host:
                restart_required.append("reverse_ws_host")
            if previous.reverse_ws_port != current.reverse_ws_port:
                restart_required.append("reverse_ws_port")
            if previous.reverse_ws_path != current.reverse_ws_path:
                restart_required.append("reverse_ws_path")

        self.adapter.ws_url = current.ws_url
        self.adapter.reverse_host = current.reverse_ws_host
        self.adapter.reverse_port = current.reverse_ws_port
        self.adapter.reverse_path = current.reverse_ws_path
        self.adapter.token = current.token
        self.adapter.mode = current.mode

        if reconnect_forward and self.adapter._ws_forward and self._main_loop:
            log.info("OneBot forward settings changed, reconnecting current forward WS")
            self._main_loop.create_task(self.adapter._ws_forward.close())

        if reconnect_reverse and self.adapter._ws_reverse and self._main_loop:
            log.info("OneBot token changed, closing current reverse WS to require re-auth")
            self._main_loop.create_task(self.adapter._ws_reverse.close())

        if restart_required:
            log.warning(
                "OneBot listener settings changed (%s); full effect requires service restart"
                % ", ".join(restart_required)
            )

    def _init_audio_and_context(self):
        """初始化音频处理器和 AppContext"""
        stt_provider = get_stt_provider(self.settings.agent.stt_provider)
        self.audio = AudioProcessor(self.adapter, self.settings, stt_provider)
        log.info(f"Voice mode: {self.settings.agent.voice_mode}, STT provider: {self.settings.agent.stt_provider}")

        self.ctx = get_app_context()
        self.ctx.register_agent(self.agent)
        self.ctx.register_mcp_manager(self.mcp_manager)
        self.ctx.register_adapter(self.adapter)
        self.ctx.register_memory_store(self.memory_store)
        self.ctx.register("bot_app", self)

        self.pipeline = MessagePipeline(self.adapter, self.agent, self.ctx, self.settings, self.audio)

    def _init_aggregators(self):
        """创建消息聚合器"""
        agg_cfg = self.config_loader.config.aggregator
        self.group_aggregator = MessageAggregator(
            initial_wait=agg_cfg.get("initial_wait", 10.0),
            extended_wait=agg_cfg.get("extended_wait", 15.0),
            on_aggregate=self.pipeline.process_aggregated_messages,
            density_enabled=agg_cfg.get("density_enabled", False),
            density_threshold=agg_cfg.get("density_threshold", 10),
            density_window=agg_cfg.get("density_window", 60.0),
            density_cooldown=agg_cfg.get("density_cooldown", 60.0),
        )
        log.info(f"Aggregator: density_enabled={agg_cfg.get('density_enabled', False)}, threshold={agg_cfg.get('density_threshold', 10)}")

        priv_cfg = self.config_loader.config.private_aggregator
        if priv_cfg.get("enabled", True):
            self.private_aggregator = MessageAggregator(
                initial_wait=priv_cfg.get("initial_wait", 3.0),
                extended_wait=priv_cfg.get("extended_wait", 5.0),
                on_aggregate=self.pipeline.process_private_aggregated_messages,
                label="私聊",
            )
            log.info(f"Private aggregator: enabled, initial_wait={priv_cfg.get('initial_wait', 3.0)}, extended_wait={priv_cfg.get('extended_wait', 5.0)}")
        else:
            self.private_aggregator = None
            log.info("Private aggregator: disabled")

        self.pipeline.set_aggregators(self.group_aggregator, self.private_aggregator)

        self.ctx.register_aggregator(self.group_aggregator)
        if self.private_aggregator:
            self.ctx.register("private_aggregator", self.private_aggregator)
        self.ctx.register_preset_manager(self.preset_manager)
        log.success("All components registered to AppContext")

    def _init_event_handlers(self):
        """注册消息和事件处理器"""
        self.adapter.on_message(self.handle_message)
        self.adapter.on_event(self.handle_event)

    async def _start_admin(self):
        """启动 Admin Console"""
        from src.admin.startup import start_admin_server
        self._admin_port = self.config_loader.config.admin.get("port", 8088)
        await start_admin_server(port=self._admin_port)

    def _log_startup_banner(self):
        """输出启动完成日志"""
        log.info("=" * 60)
        log.info("Bot is running! Waiting for messages...")
        log.info(f"Triggers: @bot, or mention: {self.bot_names}")
        log.info(f"Admin Console: http://localhost:{self._admin_port}")
        log.info("Press Ctrl+C to stop")
        log.info("=" * 60)

    async def stop(self):
        """优雅关闭"""
        from src.admin.startup import stop_admin_server

        if self.group_aggregator:
            await self.group_aggregator.flush_all()
        if self.private_aggregator:
            await self.private_aggregator.flush_all()
        if self.adapter:
            await self.adapter.stop()
        if self.mcp_manager:
            await self.mcp_manager.stop()
        # Telegram 清理
        if getattr(self, "_news_monitor", None):
            await self._news_monitor.stop()
        if getattr(self, "_tg_adapter", None):
            await self._tg_adapter.stop()
        await stop_admin_server()
        log.info("Bot stopped")

    def on_env_reload(self):
        """当 .env 发生变化时，重新加载 settings 并刷新运行时。"""
        if self._main_loop:
            self._main_loop.call_soon_threadsafe(self._handle_env_reload)

    def _handle_env_reload(self):
        """在主事件循环中处理 .env 热更新。"""
        previous_settings = self.settings
        self.settings = load_settings()

        if not previous_settings or self.settings.log_level != previous_settings.log_level:
            setup_logger(level=self.settings.log_level)
            log.info(f"Logger level updated: {self.settings.log_level}")

        self._apply_agent_behavior_settings()
        self._refresh_audio_runtime()
        self._apply_onebot_runtime_settings(previous_settings)

        new_api_key = os.getenv("OPENAI_API_KEY", "")
        new_base_url = os.getenv("OPENAI_API_BASE", "")
        new_model = os.getenv("DEFAULT_MODEL", self.settings.llm.default_model)

        if new_api_key != self.agent.api_key or new_base_url != self.agent.base_url or new_model != self.agent.model:
            self._refresh_agent_runtime(
                reason=".env changed",
                api_key=new_api_key,
                base_url=new_base_url,
                model=new_model,
            )
        else:
            self._refresh_agent_runtime(reason=".env changed")

    def on_config_reload(self, config):
        """当 config.yaml 发生变化时，刷新 Agent 运行时配置。"""
        if self._main_loop:
            self._main_loop.call_soon_threadsafe(self._handle_config_reload)

    def _handle_config_reload(self):
        """在主事件循环中处理 config.yaml 热更新。"""
        self._refresh_agent_runtime(reason="config.yaml changed")

    def _refresh_agent_runtime(
        self,
        reason: str,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        """刷新 Agent 的 LLM / FallbackLLM / 默认系统提示词。"""
        if not self.agent or not self.preset_manager:
            return

        resolved_api_key = api_key if api_key is not None else self.agent.api_key
        resolved_base_url = base_url if base_url is not None else self.agent.base_url
        resolved_model = model if model is not None else self.agent.model

        preset_name = self.settings.agent.default_preset
        default_preset = self.preset_manager.get(preset_name) or self.preset_manager.get_default()

        log.info(f"Refreshing agent runtime ({reason}): model={resolved_model}, base_url={resolved_base_url[:30]}...")

        self.agent.api_key = resolved_api_key
        self.agent.base_url = resolved_base_url
        self.agent.model = resolved_model
        self.agent.default_system_prompt = default_preset.system_prompt
        self.agent._fallback_llm = self._create_fallback_llm(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
        )
        self.agent.graph = self.agent._create_graph()
        log.success("Agent runtime refreshed")

    def _record_runtime_event(self, event_name: str, status: str, detail: str = ""):
        event = self._runtime_events.setdefault(
            event_name,
            {"count": 0, "last_at": None, "last_status": "idle", "last_detail": ""},
        )
        event["count"] += 1
        event["last_at"] = datetime.now().isoformat(timespec="seconds")
        event["last_status"] = status
        event["last_detail"] = detail

    def get_runtime_status(self) -> dict:
        tg_cfg = self.config_loader.config._raw.get("telegram", {}) if self.config_loader else {}
        fallback_models = []
        if self.config_loader and self.agent:
            fallback_models = self.config_loader.get_fallback_llm_models(
                api_key=self.agent.api_key,
                base_url=self.agent.base_url,
            )

        telegram_adapter = getattr(self, "_tg_adapter", None)
        telegram_client = getattr(telegram_adapter, "_client", None)
        telegram_connected = bool(telegram_client and telegram_client.is_connected())

        reverse_endpoint = None
        if self.adapter:
            reverse_endpoint = f"ws://{self.adapter.reverse_host}:{self.adapter.reverse_port}{self.adapter.reverse_path}"

        return {
            "admin": {
                "port": self._admin_port,
                "static_ready": Path("src/admin/static/index.html").exists(),
            },
            "agent": {
                "model": self.agent.model if self.agent else None,
                "base_url": self.agent.base_url if self.agent else None,
                "voice_mode": self.settings.agent.voice_mode if self.settings else None,
                "default_preset": self.settings.agent.default_preset if self.settings else None,
                "fallback_models": fallback_models,
                "fallback_count": len(fallback_models),
            },
            "onebot": {
                "mode": self.adapter.mode if self.adapter else None,
                "connected": bool(self.adapter and self.adapter.connected),
                "forward_connected": bool(self.adapter and self.adapter.forward_connected),
                "reverse_connected": bool(self.adapter and self.adapter.reverse_connected),
                "ws_url": self.adapter.ws_url if self.adapter else None,
                "reverse_endpoint": reverse_endpoint,
                "token_configured": bool(self.adapter and self.adapter.token),
            },
            "telegram": {
                "enabled": bool(tg_cfg.get("enabled", False)),
                "running": bool(telegram_adapter and telegram_adapter._running),
                "connected": telegram_connected,
                "session_path": getattr(telegram_adapter, "session_path", None),
                "has_proxy": bool(getattr(telegram_adapter, "proxy", None)),
                "reconnect_attempt": getattr(telegram_adapter, "_reconnect_attempt", 0),
                "last_error": getattr(telegram_adapter, "_last_error", None),
                "last_error_at": getattr(telegram_adapter, "_last_error_at", None),
                "last_connected_at": getattr(telegram_adapter, "_last_connected_at", None),
                "monitor_channels": list(tg_cfg.get("monitor", {}).get("groups", [])),
                "monitor_keywords": list(tg_cfg.get("monitor", {}).get("keywords", [])),
            },
            "reloads": self._runtime_events,
            "behavior": {
                "allow_at": self.allow_at,
                "allow_private": self.allow_private,
                "allow_all_group": self.allow_all_group,
                "bot_names": self.bot_names,
            },
        }

    def _log_incoming_message(self, event: OneBotEvent, parsed, segments: list) -> tuple[str, str, str]:
        if parsed.has_files():
            log.info(f"文件消息原始段: {segments}")

        text_desc = make_text_description(parsed)
        plain_text = parsed.text.strip()
        sender = event.sender_nickname

        if event.is_group:
            log.info(f"[群 {event.group_id}] {sender}({event.user_id}): {text_desc}")
        else:
            log.info(f"[私聊 {event.user_id}] {sender}: {text_desc}")

        return text_desc, plain_text, sender

    def _should_respond(self, event: OneBotEvent, plain_text: str) -> bool:
        if event.is_private and self.allow_private:
            return True

        if event.is_group:
            if self.allow_all_group:
                return True
            if self.allow_at and self.adapter.self_id and event.is_at_me(self.adapter.self_id):
                return True

        plain_text_lower = plain_text.lower()
        return any(name.lower() in plain_text_lower for name in self.bot_names)

    async def _fetch_message_context(self, parsed) -> tuple[str | None, str | None, list[str]]:
        reply_context = None
        forward_summary = None
        forward_image_urls = []

        if parsed.has_reply() and parsed.reply_id:
            reply_context = await fetch_reply_context(self.adapter, parsed.reply_id)

        if parsed.has_forward() and parsed.forward_id:
            forward_summary, forward_image_urls = await fetch_forward_content(self.adapter, parsed.forward_id)

        return reply_context, forward_summary, forward_image_urls

    async def _prepare_audio_content(self, parsed, plain_text: str) -> tuple[str, str | None, str | None]:
        audio_text = None
        audio_path = None
        updated_text = plain_text

        if not parsed.has_record:
            return updated_text, audio_text, audio_path

        if self.audio.should_use_native_audio():
            result = await self.audio.resolve_audio(parsed)
            if result:
                _, _, audio_path = result
            if not audio_path:
                voice_label = "[语音消息]"
                updated_text = f"{updated_text}\n{voice_label}" if updated_text else voice_label
            return updated_text, audio_text, audio_path

        audio_text, audio_path = await self.audio.process_voice(parsed)
        if audio_text:
            voice_label = f"[语音转文字]: {audio_text}"
            updated_text = f"{updated_text}\n{voice_label}" if updated_text else voice_label
        elif audio_path:
            voice_label = "[语音消息]"
            updated_text = f"{updated_text}\n{voice_label}" if updated_text else voice_label

        return updated_text, audio_text, audio_path

    def _build_pending_message(
        self,
        event: OneBotEvent,
        parsed,
        sender: str,
        plain_text: str,
        all_image_urls: list[str],
        reply_context: str | None,
        forward_summary: str | None,
        audio_text: str | None,
        audio_path: str | None,
    ) -> PendingMessage:
        return PendingMessage(
            sender_name=sender,
            sender_qq=event.user_id,
            message_id=event.message_id or 0,
            text=plain_text,
            image_urls=all_image_urls,
            reply_context=reply_context,
            reply_to_id=parsed.reply_id,
            at_targets=parsed.at_targets or [],
            forward_summary=forward_summary,
            file_descriptions=get_file_descriptions(parsed) if parsed.has_files() else [],
            audio_text=audio_text,
            audio_path=audio_path,
            timestamp=float(event.time) if event.time else time.time(),
        )

    async def _route_message(
        self,
        event: OneBotEvent,
        parsed,
        plain_text: str,
        sender: str,
        reply_context: str | None,
        forward_summary: str | None,
        all_image_urls: list[str],
        audio_text: str | None,
        audio_path: str | None,
    ):
        if event.is_private:
            if self.private_aggregator:
                pending = self._build_pending_message(
                    event=event,
                    parsed=parsed,
                    sender=sender,
                    plain_text=plain_text,
                    all_image_urls=all_image_urls,
                    reply_context=reply_context,
                    forward_summary=forward_summary,
                    audio_text=audio_text,
                    audio_path=audio_path,
                )
                await self.private_aggregator.add_message(event.user_id, pending, event)
                return

            await self.pipeline.process_single_message(
                event=event,
                parsed=parsed,
                plain_text=plain_text,
                sender=sender,
                reply_context=reply_context,
                forward_summary=forward_summary,
                all_image_urls=all_image_urls,
                audio_path=audio_path,
            )
            return

        pending = self._build_pending_message(
            event=event,
            parsed=parsed,
            sender=sender,
            plain_text=plain_text,
            all_image_urls=all_image_urls,
            reply_context=reply_context,
            forward_summary=forward_summary,
            audio_text=audio_text,
            audio_path=audio_path,
        )
        is_at_bot = self.adapter.self_id and event.is_at_me(self.adapter.self_id)
        await self.group_aggregator.add_message(event.group_id, pending, event, immediate=is_at_bot)

    async def handle_message(self, event: OneBotEvent):
        """处理收到的消息（支持多模态 + 群消息聚合）"""
        segments = event.message if isinstance(event.message, list) else []
        parsed = parse_segments(segments)

        text_desc, plain_text, sender = self._log_incoming_message(event, parsed, segments)

        if not self._should_respond(event, plain_text):
            return

        log.debug(f"触发响应: {text_desc[:50]}")

        try:
            reply_context, forward_summary, forward_image_urls = await self._fetch_message_context(parsed)

            # 防止空消息
            all_image_urls = parsed.image_urls + forward_image_urls
            if not plain_text and not reply_context and not forward_summary and not parsed.has_images() and not forward_image_urls and not parsed.has_files() and not parsed.has_record:
                log.warning("空消息，跳过处理")
                if parsed.has_forward():
                    await self.adapter.send_msg(event, "抱歉，暂时无法读取这条合并转发消息的内容~")
                return

            plain_text, audio_text, audio_path = await self._prepare_audio_content(parsed, plain_text)

            await self._route_message(
                event=event,
                parsed=parsed,
                plain_text=plain_text,
                sender=sender,
                reply_context=reply_context,
                forward_summary=forward_summary,
                all_image_urls=all_image_urls,
                audio_text=audio_text,
                audio_path=audio_path,
            )

        except Exception as e:
            log_error(e, context="消息预处理", show_traceback=True)

    async def handle_event(self, event: OneBotEvent):
        """处理全部事件"""
        if event.post_type == "meta_event":
            if event.meta_event_type == "lifecycle":
                log.success(f"Bot connected! QQ: {event.self_id}")
            elif event.meta_event_type == "heartbeat":
                log.debug("Heartbeat")

        elif event.is_file_upload and event.file:
            await self.pipeline.handle_file_upload(event)
