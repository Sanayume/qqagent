"""Structured config management endpoints."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.admin.config_schema import build_full_config, build_schema_payload
from src.utils.config_loader import get_config_loader
from src.utils.logger import log

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_FILE = Path("config.yaml")
BACKUP_DIR = Path("config/backups")


class SaveConfigRequest(BaseModel):
    content: str


class SaveStructuredConfigRequest(BaseModel):
    values: dict[str, Any]


def _read_config_text() -> str:
    if not CONFIG_FILE.exists():
        raise HTTPException(404, "Config file not found")
    return CONFIG_FILE.read_text(encoding="utf-8")


def _read_config_data() -> dict[str, Any]:
    return get_config_loader().config._raw or {}


def _backup_current_config() -> None:
    if not CONFIG_FILE.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"config.yaml.{timestamp}.bak"
    shutil.copy2(CONFIG_FILE, backup_path)

    backups = sorted(BACKUP_DIR.glob("config.yaml.*.bak"), key=lambda item: item.stat().st_mtime)
    for old_backup in backups[:-10]:
        old_backup.unlink(missing_ok=True)


def _write_config_data(data: dict[str, Any]) -> str:
    _backup_current_config()
    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)
    CONFIG_FILE.write_text(yaml_text, encoding="utf-8")
    return yaml_text


@router.get("")
async def get_config():
    return {"content": _read_config_text()}


@router.get("/schema")
async def get_config_schema():
    raw_data = _read_config_data()
    payload = build_schema_payload(raw_data)
    payload["content"] = _read_config_text()
    payload["path"] = str(CONFIG_FILE)
    return payload


@router.post("")
async def save_config(req: SaveConfigRequest):
    try:
        yaml.safe_load(req.content)
        _backup_current_config()
        CONFIG_FILE.write_text(req.content, encoding="utf-8")
        return {"status": "ok", "message": "Config saved successfully"}
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML format: {e}")
    except Exception as e:
        log.error(f"Error saving config: {e}")
        raise HTTPException(500, f"Error saving config: {e}")


@router.post("/structured")
async def save_structured_config(req: SaveStructuredConfigRequest):
    try:
        current_raw = _read_config_data()
        merged = build_full_config(current_raw=current_raw, submitted=req.values)
        yaml_text = _write_config_data(merged)
        return {
            "status": "ok",
            "message": "Structured config saved successfully",
            "content": yaml_text,
            "values": build_schema_payload(merged)["values"],
        }
    except Exception as e:
        log.error(f"Error saving structured config: {e}")
        raise HTTPException(500, f"Error saving structured config: {e}")
