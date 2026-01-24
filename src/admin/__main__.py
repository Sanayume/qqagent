"""
Admin Console 入口模块

使用方式:
    python -m src.admin
"""

import uvicorn
from src.admin.app import app


def main():
    """启动 Admin Console 服务器"""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8088,
        log_level="info",
    )


if __name__ == "__main__":
    main()
