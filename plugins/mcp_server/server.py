#!/usr/bin/env python3
"""
MindKernel MCP Server
=====================
JSON-RPC 2.0 over stdio，符合 MCP 协议规范。

启动方式（stdio）:
  python -m mindkernel.plugins.mcp_server.server
  或通过 mcporter 调用

工具列表:
  - mindkernel_retain   写入记忆
  - mindkernel_recall  查询记忆/经验
  - mindkernel_reflect 对记忆执行反思流程
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

# 确保 mindkernel 根在 path 中
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.mcp_server.tools import TOOLS

# ---------------------------------------------------------------------------
# MCP Protocol Types
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"


def jsonrpc_response(req_id: int | str | None, result: dict) -> dict:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "result": result,
    }


def jsonrpc_error(req_id: int | str | None, code: int, message: str, data=None) -> dict:
    err = {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if data is not None:
        err["error"]["data"] = data
    return err


# MCP error codes
ERR_PARSE_ERROR = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL_ERROR = -32000

# MCP capability constants
PROTOCOL_VERSION = "2024-11-05"


def build_handlers():
    """Build request handlers dict keyed by method name."""
    return {
        "initialize": handle_initialize,
        "tools/list": handle_tools_list,
        "tools/call": handle_tools_call,
        "ping": handle_ping,
    }


# ---------------------------------------------------------------------------
# Request Handlers
# ---------------------------------------------------------------------------

def handle_initialize(params: dict, req_id) -> dict:
    # 声明 server 能力
    server_info = {
        "name": "mindkernel",
        "version": "0.1.0",
    }
    capabilities = {
        "tools": {},
    }
    protocol_version = params.get("protocolVersion", PROTOCOL_VERSION)

    # 响应时带上 protocol version 确认
    return jsonrpc_response(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "serverInfo": server_info,
        "capabilities": capabilities,
        "instructions": "MindKernel MCP Server. Use tools/list to see available tools.",
    })


def handle_tools_list(params: dict, req_id) -> dict:
    tool_list = []
    for tool in TOOLS:
        tool_list.append({
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["inputSchema"],
        })
    return jsonrpc_response(req_id, {"tools": tool_list})


def handle_tools_call(params: dict, req_id) -> dict:
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    # 查找 tool
    tool = next((t for t in TOOLS if t["name"] == tool_name), None)
    if not tool:
        return jsonrpc_error(req_id, ERR_METHOD_NOT_FOUND, f"Unknown tool: {tool_name}")

    # 调用
    try:
        result = tool["fn"](arguments)
    except Exception as e:
        tb = traceback.format_exc()
        return jsonrpc_error(req_id, ERR_INTERNAL_ERROR, f"Tool execution failed: {e}", data={"trace": tb})

    # 封装为 MCP call 结果格式
    if "error" in result:
        # 工具执行返回了业务错误，仍然返回 200，但 content 里放错误信息
        content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        is_error = True
    else:
        content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        is_error = False

    return jsonrpc_response(req_id, {
        "content": content,
        "isError": is_error,
    })


def handle_ping(params: dict, req_id) -> dict:
    return jsonrpc_response(req_id, {"pong": True})


# ---------------------------------------------------------------------------
# Transport: STDIO
# ---------------------------------------------------------------------------

def read_message() -> dict | None:
    """Read one JSON-RPC message from stdin."""
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        return json.loads(line)
    except json.JSONDecodeError as e:
        return None


def write_message(msg: dict):
    """Write one JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def send_error(req_id, code: int, message: str):
    write_message(jsonrpc_error(req_id, code, message))


# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------

def main():
    handlers = build_handlers()

    # 先等待 initialize
    initialized = False
    req_id = None

    while True:
        msg = read_message()
        if msg is None:
            break

        method = msg.get("method")
        params = msg.get("params", {})
        req_id = msg.get("id")

        # initialize 特殊处理
        if method == "initialize":
            resp = handle_initialize(params, req_id)
            write_message(resp)
            initialized = True
            continue

        if not initialized:
            send_error(req_id, ERR_INVALID_REQUEST, "Server not initialized")
            continue

        # 常规方法分发
        handler = handlers.get(method)
        if not handler:
            send_error(req_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")
            continue

        try:
            resp = handler(params, req_id)
            write_message(resp)
        except Exception as e:
            tb = traceback.format_exc()
            send_error(req_id, ERR_INTERNAL_ERROR, f"Internal error: {e}")
            sys.stderr.write(tb + "\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
