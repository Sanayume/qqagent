"""
Admin Console 启动器

在主进程中启动 Admin Console 服务器。
支持自动构建前端。
"""

import asyncio
import subprocess
import uvicorn
from pathlib import Path
from typing import Optional


_admin_task: Optional[asyncio.Task] = None

# 前端相关路径
FRONTEND_DIR = Path(__file__).parent / "frontend"
STATIC_DIR = Path(__file__).parent / "static"


def _should_build_frontend() -> bool:
    """检查是否需要构建前端"""
    # 如果 static 目录不存在或为空，需要构建
    if not STATIC_DIR.exists():
        return True

    index_html = STATIC_DIR / "index.html"
    if not index_html.exists():
        return True

    # 检查前端源码是否比构建产物更新
    if not FRONTEND_DIR.exists():
        return False  # 没有前端源码，无法构建

    src_dir = FRONTEND_DIR / "src"
    if not src_dir.exists():
        return False

    # 获取最新的源文件修改时间
    latest_src_time = 0
    for f in src_dir.rglob("*"):
        if f.is_file():
            mtime = f.stat().st_mtime
            if mtime > latest_src_time:
                latest_src_time = mtime

    # 获取构建产物时间
    build_time = index_html.stat().st_mtime

    return latest_src_time > build_time


def _build_frontend() -> bool:
    """构建前端，返回是否成功"""
    from src.utils.logger import log

    if not FRONTEND_DIR.exists():
        log.warning("前端源码目录不存在，跳过构建")
        return False

    package_json = FRONTEND_DIR / "package.json"
    if not package_json.exists():
        log.warning("package.json 不存在，跳过构建")
        return False

    log.info("🔨 正在构建前端...")

    try:
        # 检查 node_modules
        node_modules = FRONTEND_DIR / "node_modules"
        if not node_modules.exists():
            log.info("📦 安装前端依赖...")
            subprocess.run(
                ["npm", "install"],
                cwd=FRONTEND_DIR,
                check=True,
                capture_output=True,
            )

        # 构建
        result = subprocess.run(
            ["npx", "vite", "build"],
            cwd=FRONTEND_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        log.success("✅ 前端构建完成")
        return True

    except subprocess.CalledProcessError as e:
        log.error(f"❌ 前端构建失败: {e.stderr or e.stdout}")
        return False
    except FileNotFoundError:
        log.warning("⚠️ 未找到 npm/npx，跳过前端构建")
        return False


async def start_admin_server(host: str = "0.0.0.0", port: int = 8088, auto_build: bool = True):
    """在后台启动 Admin Console 服务器

    Args:
        host: 监听地址
        port: 监听端口
        auto_build: 是否自动构建前端（当源码更新时）
    """
    global _admin_task

    from src.utils.logger import log

    # 自动构建前端
    if auto_build and _should_build_frontend():
        _build_frontend()

    # 初始化日志服务
    from src.admin.services.log_service import get_log_service
    get_log_service()

    log.info(f"🚀 正在启动 Admin Console: http://localhost:{port}")
    
    # 创建 uvicorn config
    config = uvicorn.Config(
        "src.admin.app:app",
        host=host,
        port=port,
        log_level="warning",  # 减少 uvicorn 自身的日志噪音
        access_log=False,
    )
    server = uvicorn.Server(config)
    
    # 作为后台任务运行
    _admin_task = asyncio.create_task(server.serve())
    
    log.success(f"✅ Admin Console 已启动: http://localhost:{port}")


async def stop_admin_server():
    """停止 Admin Console 服务器"""
    global _admin_task
    if _admin_task:
        _admin_task.cancel()
        try:
            await _admin_task
        except asyncio.CancelledError:
            pass
        _admin_task = None
