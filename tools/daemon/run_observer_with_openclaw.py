#!/usr/bin/env python3
"""
MindKernel Daemon + OpenClaw 观察层编排脚本

启动两个进程：
1. openclaw_event_adapter — 每30秒从 OpenClaw transcript 读取新消息，写入 events JSONL
2. memory_observer_daemon — 消费 adapter 写入的事件，走完整 pipeline

Usage:
  python3 run_observer_with_openclaw.py [--adapter-interval 30]
  python3 run_observer_with_openclaw.py --stop   # 停止
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_SCRIPT = ROOT / "tools" / "daemon" / "openclaw_event_adapter.py"
DAEMON_SCRIPT = ROOT / "tools" / "daemon" / "memory_observer_daemon_v0_2.py"
EVENTS_FILE = ROOT / "data" / "fixtures" / "daemon_events_openclaw.jsonl"
PID_FILE = ROOT / "data" / "daemon" / "observer_openclaw.pid"


def write_pid(pid: int):
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop():
    if PID_FILE.exists():
        old_pid = int(PID_FILE.read_text().strip())
        if is_running(old_pid):
            print(f"[observer] killing old process {old_pid}")
            os.kill(old_pid, signal.SIGTERM)
        PID_FILE.unlink()
        print("[observer] stopped")


def main():
    parser = argparse.ArgumentParser(description="MindKernel + OpenClaw 观察层编排")
    parser.add_argument("--adapter-interval", type=int, default=30,
                        help="adapter 轮询间隔秒数（默认30）")
    parser.add_argument("--daemon-mode", default="poll",
                        choices=["poll", "tail"],
                        help="daemon 运行模式（默认 poll）")
    parser.add_argument("--stop", action="store_true", help="停止正在运行的进程")
    args = parser.parse_args()

    if args.stop:
        stop()
        return

    # 停止旧进程
    stop()

    my_pid = os.getpid()
    write_pid(my_pid)
    print(f"[observer] pid={my_pid}")

    # 清理函数
    def cleanup(signum, frame):
        print("[observer] received signal, shutting down...")
        if adapter_proc.poll() is None:
            adapter_proc.terminate()
        if daemon_proc.poll() is None:
            daemon_proc.terminate()
        daemon_proc.wait()
        adapter_proc.wait()
        print("[observer] stopped")
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    print(f"[observer] starting adapter (interval={args.adapter_interval}s)")
    print(f"[observer] starting daemon (mode={args.daemon_mode})")
    print(f"[observer] events file: {EVENTS_FILE}")

    # 启动 adapter（轮询 OpenClaw transcript）
    adapter_proc = subprocess.Popen(
        [sys.executable, str(ADAPTER_SCRIPT),
         "--poll", "--interval", str(args.adapter_interval)],
        cwd=str(ROOT),
    )

    # 短暂等待，确保 adapter 先跑起来
    time.sleep(1)

    # 启动 daemon（消费 adapter 写入的事件）
    daemon_proc = subprocess.Popen(
        [sys.executable, str(DAEMON_SCRIPT),
         "--mode", args.daemon_mode,
         "--events-file", str(EVENTS_FILE)],
        cwd=str(ROOT),
    )

    print(f"[observer] adapter pid={adapter_proc.pid}")
    print(f"[observer] daemon pid={daemon_proc.pid}")
    print("[observer] running. Press Ctrl+C to stop.")

    # 等待任意一个子进程退出（通常是因为被 SIGTERM）
    try:
        # 优先等待 adapter，daemon 由 signal handler 管理
        while adapter_proc.poll() is None and daemon_proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup(None, None)


if __name__ == "__main__":
    main()
