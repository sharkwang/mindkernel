"""Plugin configuration."""

from __future__ import annotations

import os
from pathlib import Path

# 默认路径（从 plugins/mcp_server/ 向上两级到 mindkernel 根）
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = DEFAULT_ROOT / "data" / "mindkernel_v0_1.sqlite"
DEFAULT_SCHEMA_DIR = DEFAULT_ROOT / "schemas"

# 环境变量覆盖
DB_PATH = Path(os.getenv("MINDKERNEL_DB", DEFAULT_DB))
SCHEMA_DIR = Path(os.getenv("MINDKERNEL_SCHEMA_DIR", DEFAULT_SCHEMA_DIR))

# MCP 服务器元信息
SERVER_NAME = "mindkernel"
SERVER_VERSION = "0.1.0"
