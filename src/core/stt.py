"""
STT (Speech-to-Text) 可插拔接口

用户可实现 STTProvider 接口接入自己的 STT 服务。
"""

from abc import ABC, abstractmethod

from src.utils.logger import log


class STTProvider(ABC):
    """STT 服务抽象接口"""

    @abstractmethod
    async def transcribe(self, audio_data: bytes, audio_format: str) -> str:
        """将音频转为文字

        Args:
            audio_data: 音频原始字节
            audio_format: 音频格式 (amr, silk, wav, mp3, etc.)

        Returns:
            转写文本
        """
        ...


class NoopSTTProvider(STTProvider):
    """空实现，STT 未配置时使用"""

    async def transcribe(self, audio_data: bytes, audio_format: str) -> str:
        log.debug("STT 未配置，跳过语音转写")
        return ""


def get_stt_provider(provider: str = "noop", **kwargs) -> STTProvider:
    """工厂函数，根据配置创建 STT 提供者

    Args:
        provider: 提供者名称 (noop / 自定义)
        **kwargs: 传给提供者的参数

    Returns:
        STTProvider 实例
    """
    if provider == "noop":
        return NoopSTTProvider()

    log.warning(f"未知的 STT provider: {provider}，使用 noop")
    return NoopSTTProvider()
