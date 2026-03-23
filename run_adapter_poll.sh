#!/bin/bash
# 定时 poll 浏览器书签 + 文件系统适配器，写入 MindKernel 记忆
# 用法：加入 cron: */30 * * * * /Users/zhengwang/projects/mindkernel/run_adapter_poll.sh

API_URL="http://127.0.0.1:18793/api/v1/adapters/poll"
API_KEY_FILE="/Users/zhengwang/.mindkernel/api_key"

API_KEY=$(cat "$API_KEY_FILE" 2>/dev/null)
if [ -z "$API_KEY" ]; then
    echo "[MindKernel Adapter Poll] API key not found at $API_KEY_FILE"
    exit 1
fi

RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "X-MindKernel-Key: $API_KEY" \
    -H "Content-Type: application/json")

echo "[$(date)] MindKernel Adapter Poll: $RESPONSE"
