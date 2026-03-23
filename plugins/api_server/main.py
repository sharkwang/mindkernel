"""MindKernel API Server — FastAPI application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure core modules are importable
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plugins.api_server.routers import health, recall, reflect, retain, prune, adapters, knowledge, kg_ops, opinions

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

VERSION = "0.3.0"

app = FastAPI(
    title="MindKernel API",
    description="MindKernel v0.3 REST API — 记忆 / 检索 / 反思",
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地服务，宽松即可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(retain.router, prefix="/api/v1", tags=["retain"])
app.include_router(recall.router, prefix="/api/v1", tags=["recall"])
app.include_router(reflect.router, prefix="/api/v1", tags=["reflect"])
app.include_router(prune.router, prefix="/api/v1", tags=["prune"])
app.include_router(adapters.router, prefix="/api/v1", tags=["adapters"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["knowledge"])
app.include_router(kg_ops.router, prefix="/api/v1", tags=["knowledge"])
app.include_router(opinions.router, prefix="/api/v1", tags=["opinions"])


@app.get("/")
def root():
    return {
        "service": "MindKernel API",
        "version": VERSION,
        "docs": "/docs",
    }


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="MindKernel REST API Server")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址")
    parser.add_argument("--port", type=int, default=18792, help="端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    uvicorn.run(
        "plugins.api_server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=False,
    )


if __name__ == "__main__":
    main()
