"""
预设加载器

从 config.yaml 和 config/presets/*.yaml 加载角色预设。
支持：
- 从 config.yaml 的 presets 字段加载
- 从 config/presets/ 目录下的 YAML 文件加载
- 通过关键词匹配预设
- 热重载 (通过 ConfigLoader 回调)
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field

from src.utils.logger import log


@dataclass
class Preset:
    """角色预设"""

    name: str
    system_prompt: str
    keywords: list[str] = field(default_factory=list)
    input_template: str = "{message}"
    # 可扩展字段
    description: str = ""
    author: str = ""


class PresetManager:
    """预设管理器

    从多个来源加载预设：
    1. config.yaml 中的 presets 字段 (适合简单预设)
    2. config/presets/*.yaml 文件 (适合复杂预设)
    """

    def __init__(
        self,
        config_loader=None,
        preset_dir: Path | str | None = None,
    ):
        """初始化预设管理器

        Args:
            config_loader: ConfigLoader 实例 (可选，用于从 config.yaml 加载)
            preset_dir: 预设文件目录 (默认 config/presets)
        """
        self._presets: dict[str, Preset] = {}
        self._keyword_map: dict[str, str] = {}  # keyword -> preset_name

        self.config_loader = config_loader
        self.preset_dir = Path(preset_dir) if preset_dir else Path("config/presets")

        # 加载预设
        self._load_all()

        # 注册配置更新回调
        if config_loader:
            config_loader.add_callback(self._on_config_update)

    def _on_config_update(self, config):
        """配置更新时重新加载"""
        log.info("PresetManager: Reloading presets due to config change")
        self._load_all()

    def _load_all(self):
        """加载所有预设"""
        self._presets.clear()
        self._keyword_map.clear()

        # 1. 从 config.yaml 加载
        if self.config_loader:
            self._load_from_config()

        # 2. 从文件加载
        self._load_from_files()

        # 3. 确保有默认预设
        self._ensure_default()

        log.info(f"PresetManager loaded {len(self._presets)} presets: {list(self._presets.keys())}")

    def _load_from_config(self):
        """从 config.yaml 加载预设"""
        try:
            presets_data = self.config_loader.config.presets
            if not presets_data:
                return

            for name, data in presets_data.items():
                if isinstance(data, dict):
                    preset = Preset(
                        name=name,
                        system_prompt=data.get("system_prompt", ""),
                        keywords=data.get("keywords", []),
                        input_template=data.get("input_template", "{message}"),
                        description=data.get("description", ""),
                        author=data.get("author", ""),
                    )
                    self._add_preset(preset)
                elif isinstance(data, str):
                    # 简化格式: name: "system_prompt"
                    preset = Preset(name=name, system_prompt=data)
                    self._add_preset(preset)

        except Exception as e:
            log.warning(f"Failed to load presets from config: {e}")

    def _load_from_files(self):
        """从 config/presets/*.yaml 加载预设"""
        if not self.preset_dir.exists():
            log.debug(f"Preset directory not found: {self.preset_dir}")
            return

        for file_path in self.preset_dir.glob("*.yaml"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data or not isinstance(data, dict):
                    continue

                # 使用文件名作为默认名称
                name = data.get("name", file_path.stem)

                preset = Preset(
                    name=name,
                    system_prompt=data.get("system_prompt", ""),
                    keywords=data.get("keywords", []),
                    input_template=data.get("input_template", "{message}"),
                    description=data.get("description", ""),
                    author=data.get("author", ""),
                )
                self._add_preset(preset)
                log.debug(f"Loaded preset from file: {file_path.name}")

            except Exception as e:
                log.warning(f"Failed to load preset from {file_path}: {e}")

    def _add_preset(self, preset: Preset):
        """添加预设到管理器"""
        self._presets[preset.name] = preset

        # 建立关键词索引
        for keyword in preset.keywords:
            self._keyword_map[keyword.lower()] = preset.name

    def _ensure_default(self):
        """确保存在默认预设"""
        if "default" not in self._presets:
            self._presets["default"] = Preset(
                name="default",
                system_prompt="你是一个有帮助的 AI 助手。",
            )

    def get(self, name: str) -> Preset | None:
        """通过名称获取预设

        Args:
            name: 预设名称

        Returns:
            预设对象，如果不存在返回 None
        """
        return self._presets.get(name)

    def get_by_keyword(self, text: str) -> Preset | None:
        """通过关键词匹配预设

        Args:
            text: 文本内容，会在其中搜索关键词

        Returns:
            匹配的预设对象，如果没有匹配返回 None
        """
        text_lower = text.lower()
        for keyword, preset_name in self._keyword_map.items():
            if keyword in text_lower:
                return self._presets.get(preset_name)
        return None

    def get_default(self) -> Preset:
        """获取默认预设"""
        return self._presets.get("default", Preset(name="default", system_prompt=""))

    def list_all(self) -> list[str]:
        """获取所有预设名称"""
        return list(self._presets.keys())

    def list_presets(self) -> list[Preset]:
        """获取所有预设对象"""
        return list(self._presets.values())
