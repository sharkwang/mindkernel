#!/bin/bash
# MindKernel REST API Server 启动脚本
# 用法: ./run_api_server.sh [--port 18793]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
PORT="${1:-18793}"

cd "$ROOT_DIR"

echo "[MindKernel API] 启动服务 on http://127.0.0.1:$PORT"
echo "[MindKernel API] 文档: http://127.0.0.1:$PORT/docs"
echo "[MindKernel API] API Key: $(cat ~/.mindkernel/api_key 2>/dev/null || echo '未生成，请先运行一次 API')"

"$VENV_PYTHON" -m uvicorn \
    plugins.api_server.main:app \
    --host 127.0.0.1 \
    --port "$PORT"
