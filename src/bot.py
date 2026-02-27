"""
BotApp - QQ Agent 主应用类

职责：组件生命周期管理、触发检测、消息路由。
处理逻辑已拆分到 src/processing/ 和 src/core/message_fetch。
"""

import asyncio
import os
import time

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

        # 触发配置（从 settings 中提取，供 handle_message 使用）
        self.bot_names: list[str] = []
        self.allow_at: bool = True
        self.allow_private: bool = True
        self.allow_all_group: bool = False

    async def start(self):
        """初始化所有组件并启动"""
        env_loader = get_env_loader()
        self._init_config()
        self._init_storage()
        all_tools = await self._init_tools()
        self._init_agent(all_tools)
        env_loader.add_callback(self.on_env_reload)
        self._init_adapter()
        self._init_audio_and_context()
        self._init_aggregators()
        self._init_event_handlers()
        await self._start_admin()
        self._log_startup_banner()

        try:
            await self.adapter.start()
        except KeyboardInterrupt:
            log.info("Interrupted by user")
        finally:
            await self.stop()

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
        """从 config.yaml 构建 FallbackLLM，不满足条件时返回 None"""
        import yaml as _yaml
        api_key = api_key or self.settings.llm.openai_api_key
        base_url = base_url or self.settings.llm.openai_api_base
        try:
            with open("config.yaml", "r", encoding="utf-8") as _f:
                _raw = _yaml.safe_load(_f) or {}
            model_list = (_raw.get("llm") or {}).get("models", [])
            if len(model_list) >= 2:
                for cfg in model_list:
                    cfg.setdefault("api_key", api_key)
                    cfg.setdefault("base_url", base_url)
                    cfg.setdefault("model", self.settings.llm.default_model)
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

        self.bot_names = self.settings.agent.bot_names
        self.allow_at = self.settings.agent.allow_at_reply
        self.allow_private = self.settings.agent.allow_private
        self.allow_all_group = self.settings.agent.allow_all_group_msg
        log.info(f"Bot names: {self.bot_names}")
        log.info(f"Allow @: {self.allow_at}, Allow private: {self.allow_private}, Allow all group: {self.allow_all_group}")

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
        await stop_admin_server()
        log.info("Bot stopped")

    def on_env_reload(self):
        """当 .env 发生变化时，重新创建 LLM 实例"""
        new_api_key = os.getenv("OPENAI_API_KEY", "")
        new_base_url = os.getenv("OPENAI_API_BASE", "")
        new_model = os.getenv("DEFAULT_MODEL", self.settings.llm.default_model)

        if new_api_key != self.agent.api_key or new_base_url != self.agent.base_url or new_model != self.agent.model:
            log.info(f"Updating agent LLM config: model={new_model}, base_url={new_base_url[:30]}...")
            self.agent.api_key = new_api_key
            self.agent.base_url = new_base_url
            self.agent.model = new_model

            self.agent._fallback_llm = self._create_fallback_llm(api_key=new_api_key, base_url=new_base_url)
            self.agent.graph = self.agent._create_graph()
            log.success("Agent LLM config updated!")

    async def handle_message(self, event: OneBotEvent):
        """处理收到的消息（支持多模态 + 群消息聚合）"""
        segments = event.message if isinstance(event.message, list) else []
        parsed = parse_segments(segments)

        if parsed.has_files():
            log.info(f"文件消息原始段: {segments}")

        text_desc = make_text_description(parsed)
        plain_text = parsed.text.strip()
        sender = event.sender_nickname

        if event.is_group:
            log.info(f"[群 {event.group_id}] {sender}({event.user_id}): {text_desc}")
        else:
            log.info(f"[私聊 {event.user_id}] {sender}: {text_desc}")

        # 检查是否应该响应
        should_respond = False

        if event.is_private and self.allow_private:
            should_respond = True
        if event.is_group:
            if self.allow_all_group:
                should_respond = True
            elif self.allow_at and self.adapter.self_id and event.is_at_me(self.adapter.self_id):
                should_respond = True
        for name in self.bot_names:
            if name.lower() in plain_text.lower():
                should_respond = True
                break

        if not should_respond:
            return

        log.debug(f"触发响应: {text_desc[:50]}")

        try:
            # 获取上下文（引用消息、合并转发）
            reply_context = None
            forward_summary = None
            forward_image_urls = []

            if parsed.has_reply() and parsed.reply_id:
                reply_context = await fetch_reply_context(self.adapter, parsed.reply_id)

            if parsed.has_forward() and parsed.forward_id:
                forward_summary, forward_image_urls = await fetch_forward_content(self.adapter, parsed.forward_id)

            # 防止空消息
            all_image_urls = parsed.image_urls + forward_image_urls
            if not plain_text and not reply_context and not forward_summary and not parsed.has_images() and not forward_image_urls and not parsed.has_files() and not parsed.has_record:
                log.warning("空消息，跳过处理")
                if parsed.has_forward():
                    await self.adapter.send_msg(event, "抱歉，暂时无法读取这条合并转发消息的内容~")
                return

            # 语音处理
            audio_text = None
            audio_path = None
            if parsed.has_record:
                if self.audio.should_use_native_audio():
                    result = await self.audio.resolve_audio(parsed)
                    if result:
                        _, _, audio_path = result
                    if not audio_path:
                        voice_label = "[语音消息]"
                        plain_text = f"{plain_text}\n{voice_label}" if plain_text else voice_label
                else:
                    audio_text, audio_path = await self.audio.process_voice(parsed)
                    if audio_text:
                        voice_label = f"[语音转文字]: {audio_text}"
                        plain_text = f"{plain_text}\n{voice_label}" if plain_text else voice_label
                    elif audio_path:
                        voice_label = "[语音消息]"
                        plain_text = f"{plain_text}\n{voice_label}" if plain_text else voice_label

            # ===== 分流：私聊走私聊聚合器，群聊走群聚合器 =====
            if event.is_private:
                if self.private_aggregator:
                    pending = PendingMessage(
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
                    await self.private_aggregator.add_message(event.user_id, pending, event)
                else:
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
            else:
                # 群聊：添加到聚合器
                pending = PendingMessage(
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
                is_at_bot = self.adapter.self_id and event.is_at_me(self.adapter.self_id)
                await self.group_aggregator.add_message(event.group_id, pending, event, immediate=is_at_bot)

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
