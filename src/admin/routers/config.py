"""
配置管理 API

提供 config.yaml 的读写接口。
直接作为文本处理以保留注释。
"""

import shutil
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.utils.logger import log

router = APIRouter(prefix="/api/config", tags=["配置"])

CONFIG_FILE = Path("config.yaml")
BACKUP_DIR = Path("config/backups")

class SaveConfigRequest(BaseModel):
    content: str

@router.get("")
async def get_config():
    """获取配置内容 (原始 YAML)"""
    if not CONFIG_FILE.exists():
        raise HTTPException(404, "Config file not found")
        
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        log.error(f"Error reading config: {e}")
        raise HTTPException(500, f"Error reading config: {e}")

@router.post("")
async def save_config(req: SaveConfigRequest):
    """保存配置"""
    try:
        # 1. 创建备份
        if CONFIG_FILE.exists():
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUP_DIR / f"config.yaml.{timestamp}.bak"
            shutil.copy2(CONFIG_FILE, backup_path)
            
            # 清理旧备份 (保留最近 10 个)
            backups = sorted(BACKUP_DIR.glob("config.yaml.*.bak"), key=os.path.getmtime)
            for old_backup in backups[:-10]:
                old_backup.unlink()

        # 2. 验证 YAML 格式 (简单验证)
        import yaml
        yaml.safe_load(req.content)

        # 3. 保存
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(req.content)
            
        return {"status": "ok", "message": "Config saved successfully"}
        
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML format: {e}")
    except Exception as e:
        log.error(f"Error saving config: {e}")
        raise HTTPException(500, f"Error saving config: {e}")

import os
