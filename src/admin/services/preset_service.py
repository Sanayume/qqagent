"""
预设管理服务

负责读取、保存、删除 config/presets/ 下的 YAML 预设文件。
"""

import os
import yaml
from pathlib import Path
from typing import List, Dict, Any

from src.utils.logger import log

PRESETS_DIR = Path("config/presets")

class PresetService:
    """预设服务"""

    def __init__(self, presets_dir: Path = PRESETS_DIR):
        self.presets_dir = presets_dir
        # 确保目录存在
        if not self.presets_dir.exists():
            self.presets_dir.mkdir(parents=True, exist_ok=True)

    def list_presets(self) -> List[str]:
        """列出所有预设文件名（不含 .yaml 后缀）"""
        if not self.presets_dir.exists():
            return []
        
        files = []
        for f in self.presets_dir.glob("*.yaml"):
            files.append(f.stem)
        return sorted(files)

    def get_preset(self, name: str) -> Dict[str, Any] | None:
        """获取预设内容"""
        file_path = self.presets_dir / f"{name}.yaml"
        if not file_path.exists():
            return None
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            log.error(f"Error reading preset {name}: {e}")
            return None

    def get_preset_raw(self, name: str) -> str | None:
        """获取预设原始 YAML 内容"""
        file_path = self.presets_dir / f"{name}.yaml"
        if not file_path.exists():
            return None
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            log.error(f"Error reading preset {name}: {e}")
            return None

    def save_preset(self, name: str, content: str) -> bool:
        """保存预设 (直接保存 YAML 字符串)"""
        try:
            # 验证 YAML 格式
            yaml.safe_load(content)
            
            file_path = self.presets_dir / f"{name}.yaml"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except yaml.YAMLError as e:
            log.error(f"Invalid YAML format for preset {name}: {e}")
            raise ValueError(f"无效的 YAML 格式: {e}")
        except Exception as e:
            log.error(f"Error saving preset {name}: {e}")
            return False

    def delete_preset(self, name: str) -> bool:
        """删除预设"""
        file_path = self.presets_dir / f"{name}.yaml"
        if not file_path.exists():
            return False
            
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            log.error(f"Error deleting preset {name}: {e}")
            return False


# 全局单例
_preset_service: PresetService | None = None

def get_preset_service() -> PresetService:
    global _preset_service
    if _preset_service is None:
        _preset_service = PresetService()
    return _preset_service
