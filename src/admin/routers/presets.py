"""
预设管理 API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.admin.services.preset_service import get_preset_service

router = APIRouter(prefix="/api/presets", tags=["预设"])

class SavePresetRequest(BaseModel):
    content: str  # YAML 字符串

@router.get("")
async def list_presets():
    """获取所有预设列表"""
    svc = get_preset_service()
    return svc.list_presets()

@router.get("/{name}")
async def get_preset(name: str):
    """获取预设内容 (原始 YAML)"""
    svc = get_preset_service()
    content = svc.get_preset_raw(name)
    if content is None:
        raise HTTPException(404, "Preset not found")
    return {"name": name, "content": content}

@router.post("/{name}")
async def create_or_update_preset(name: str, req: SavePresetRequest):
    """创建或更新预设"""
    svc = get_preset_service()
    try:
        success = svc.save_preset(name, req.content)
        if not success:
            raise HTTPException(500, "Failed to save preset")
        return {"status": "ok", "message": f"Preset '{name}' saved successfully"}
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.delete("/{name}")
async def delete_preset(name: str):
    """删除预设"""
    svc = get_preset_service()
    if not svc.delete_preset(name):
        raise HTTPException(404, "Preset not found or failed to delete")
    return {"status": "ok", "message": f"Preset '{name}' deleted"}
