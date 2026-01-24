"""
Admin Console - FastAPI 应用主体

提供 API 路由注册和静态文件服务。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.utils.logger import log
from src.admin.routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    log.info("🚀 Admin Console 启动中...")
    
    # 启动时初始化
    from src.admin.services.user_service import get_user_service
    get_user_service()  # 初始化用户服务，创建默认管理员
    
    log.success("✅ Admin Console 启动完成")
    log.info("📍 访问地址: http://localhost:8088")
    
    yield
    
    log.info("👋 Admin Console 关闭")


app = FastAPI(
    title="QQ Agent Admin Console",
    description="QQ Agent 管理控制台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置 - 开发环境允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
from src.admin.routers import logs, sandbox, mcp, presets, config, status, agent, tools
app.include_router(logs.router)
app.include_router(sandbox.router)
app.include_router(mcp.router)
app.include_router(presets.router)
app.include_router(config.router)
app.include_router(status.router)
app.include_router(agent.router)
app.include_router(tools.router)


# 静态文件服务（Vue 构建产物）
# 开发时使用 Vite 开发服务器，生产时从这里提供静态文件
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "admin-console"}
