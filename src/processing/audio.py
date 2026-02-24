"""音频处理器

从 bot.py 提取的语音相关方法：解析、转写、转码。
"""

import time
from pathlib import Path

from src.core.media import download_audio, read_local_audio, model_supports_audio, audio_to_wav
from src.session.aggregator import PendingMessage
from src.utils.logger import log


class AudioProcessor:
    def __init__(self, adapter, settings, stt_provider):
        self.adapter = adapter
        self.settings = settings
        self.stt_provider = stt_provider

    async def resolve_audio(self, parsed) -> tuple[bytes, str, str] | None:
        """获取语音数据，返回 (bytes, format, local_path) 或 None"""
        audio_data = None
        audio_mime = None

        # 1. 尝试本地路径
        if parsed.record_file and not parsed.record_file.startswith("http"):
            try:
                audio_data, audio_mime = read_local_audio(parsed.record_file)
                log.debug(f"读取本地语音: {parsed.record_file}, {audio_mime}")
            except Exception as e:
                log.warning(f"读取本地语音失败: {e}")

        # 2. 尝试 URL
        if not audio_data and parsed.record_url:
            try:
                audio_data, audio_mime = await download_audio(parsed.record_url)
                log.debug(f"下载语音: {parsed.record_url[:50]}, {audio_mime}")
            except Exception as e:
                log.warning(f"下载语音失败: {e}")

        # 3. 尝试 get_record API
        if not audio_data and parsed.record_file_id:
            try:
                result = await self.adapter.call_api("get_record", {
                    "file_id": parsed.record_file_id,
                    "out_format": "amr",
                })
                if result.get("status") == "ok":
                    file_path = result.get("data", {}).get("file", "")
                    if file_path:
                        audio_data, audio_mime = read_local_audio(file_path)
                        log.debug(f"get_record 获取语音: {file_path}")
            except Exception as e:
                log.warning(f"get_record 失败: {e}")

        if not audio_data:
            log.warning("无法获取语音数据")
            return None

        # 保存到 workspace/sound/
        save_dir = Path("workspace/sound")
        save_dir.mkdir(parents=True, exist_ok=True)

        mime_ext = {"audio/amr": ".amr", "audio/silk": ".silk", "audio/ogg": ".ogg",
                    "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/flac": ".flac",
                    "audio/mp4": ".m4a"}
        ext = mime_ext.get(audio_mime, ".amr")
        filename = f"voice_{int(time.time() * 1000)}{ext}"
        filepath = save_dir / filename
        filepath.write_bytes(audio_data)

        fmt = ext.lstrip(".")
        log.info(f"语音已保存: {filepath} ({len(audio_data)} bytes, {fmt})")
        return audio_data, fmt, str(filepath.absolute())

    async def process_voice(self, parsed) -> tuple[str | None, str | None]:
        """处理语音消息，返回 (转写文本, 本地路径)"""
        result = await self.resolve_audio(parsed)
        if not result:
            return None, None

        audio_data, fmt, local_path = result
        text = await self.stt_provider.transcribe(audio_data, fmt)
        if text:
            log.info(f"语音转写: {text[:50]}...")
        return text or None, local_path

    def should_use_native_audio(self) -> bool:
        """判断是否使用原生多模态音频"""
        mode = self.settings.agent.voice_mode
        if mode == "native":
            return True
        if mode == "stt":
            return False
        return model_supports_audio(self.settings.llm.default_model)

    def try_convert_audio(self, audio_data: bytes, fmt: str) -> tuple[bytes, str] | None:
        """尝试将音频转为 WAV，返回 (wav_bytes, "wav") 或 None"""
        if fmt == "wav":
            return audio_data, "wav"
        wav = audio_to_wav(audio_data)
        if wav:
            return wav, "wav"
        log.warning(f"音频转码失败: fmt={fmt}, 跳过")
        return None

    async def collect_audio_from_messages(self, messages: list[PendingMessage]) -> list[tuple[bytes, str]]:
        """从聚合消息中收集并转码所有音频"""
        result = []
        for msg in messages:
            if not msg.audio_path:
                continue
            try:
                p = Path(msg.audio_path)
                if not p.exists():
                    continue
                data = p.read_bytes()
                fmt = p.suffix.lstrip(".").lower()
                converted = self.try_convert_audio(data, fmt)
                if converted:
                    result.append(converted)
            except Exception as e:
                log.warning(f"读取音频失败: {e}")
        return result
