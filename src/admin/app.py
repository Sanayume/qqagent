"""FastAPI app for the admin console."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.admin.auth import verify_token
from src.admin.routers import auth
from src.admin.security import get_admin_security_warnings
from src.utils.config_loader import get_config_loader
from src.utils.logger import log


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Admin Console starting...")

    from src.admin.services.user_service import get_user_service

    get_user_service()
    for warning in get_admin_security_warnings(get_config_loader().config.admin):
        log.warning(f"Admin security warning: {warning}")

    log.success("Admin Console started")
    log.info("Visit: http://localhost:8088")
    yield
    log.info("Admin Console stopped")


app = FastAPI(
    title="QQ Agent Admin Console",
    description="QQ Agent management console",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_config_loader().config.admin.get(
        "cors_origins",
        ["http://127.0.0.1:8088", "http://localhost:8088", "http://127.0.0.1:5173", "http://localhost:5173"],
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_admin_api(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path.startswith("/api/auth/") or path == "/api/health":
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    elif get_config_loader().config.admin.get("allow_query_token", False) and request.query_params.get("token"):
        token = request.query_params.get("token", "").strip()

    if not token:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    if verify_token(token) is None:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

    return await call_next(request)


app.include_router(auth.router)
from src.admin.routers import agent, config, logs, mcp, presets, sandbox, status, tools

app.include_router(logs.router)
app.include_router(sandbox.router)
app.include_router(mcp.router)
app.include_router(presets.router)
app.include_router(config.router)
app.include_router(status.router)
app.include_router(agent.router)
app.include_router(tools.router)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "admin-console"}
