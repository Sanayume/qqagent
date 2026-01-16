"""
Web 沙盒启动入口

用法: python -m src.sandbox_web [--port PORT]
"""

import argparse
import uvicorn
from src.sandbox_web.app import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QQ Agent Web 沙盒")
    parser.add_argument("--port", type=int, default=8088, help="端口号 (默认: 8088)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="主机地址 (默认: 127.0.0.1)")
    args = parser.parse_args()

    print("启动 Web 沙盒...")
    print(f"访问 http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
