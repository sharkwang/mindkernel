#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="python3"
DAEMON="$ROOT/tools/daemon/memory_observer_daemon_v0_2.py"
STATE_DB="$ROOT/data/daemon/memory_observer_v0_2.sqlite"
PID_FILE="$ROOT/data/daemon/memory_observer_v0_2.pid"
EVENTS_FILE="${EVENTS_FILE:-$ROOT/data/fixtures/daemon_events_v0_2.jsonl}"
SCHED_DB="${SCHEDULER_DB:-$ROOT/data/mindkernel_v0_1.sqlite}"
ALLOWLIST_DEFAULT="$ROOT/data/daemon/partial_sessions.allowlist"
LOG_DIR="$ROOT/reports/daemon"
LOG_FILE="$LOG_DIR/daemon_v0_2.log"

mkdir -p "$LOG_DIR" "$ROOT/data/daemon"

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_mode() {
  local mode="$1"
  local allowlist="${2:-$ALLOWLIST_DEFAULT}"

  if is_running; then
    echo "daemon already running (pid $(cat "$PID_FILE"))"
    return 0
  fi

  local extra=()
  case "$mode" in
    off)
      extra+=(--feature-flag off)
      ;;
    shadow)
      extra+=(--feature-flag shadow)
      ;;
    partial)
      extra+=(--feature-flag partial --partial-session-allowlist "$allowlist")
      ;;
    on)
      extra+=(--feature-flag on)
      ;;
    *)
      echo "unsupported mode: $mode" >&2
      exit 2
      ;;
  esac

  # enqueue is enabled only when mode allows it; off/shadow remain observe-only
  if [[ "$mode" == "partial" || "$mode" == "on" ]]; then
    extra+=(--enable-enqueue)
  fi

  nohup "$PY" "$DAEMON" \
    --mode poll \
    --events-file "$EVENTS_FILE" \
    --state-db "$STATE_DB" \
    --pid-file "$PID_FILE" \
    --scheduler-db "$SCHED_DB" \
    --poll-interval-sec 1 \
    --max-batch 200 \
    "${extra[@]}" \
    >> "$LOG_FILE" 2>&1 &

  sleep 0.4
  if is_running; then
    echo "daemon started in mode=$mode (pid $(cat "$PID_FILE"))"
  else
    echo "daemon failed to start; check $LOG_FILE" >&2
    exit 1
  fi
}

stop_daemon() {
  if ! is_running; then
    echo "daemon not running"
    rm -f "$PID_FILE"
    return 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"
  kill -TERM "$pid" || true

  for _ in {1..20}; do
    if kill -0 "$pid" 2>/dev/null; then
      sleep 0.2
    else
      break
    fi
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" || true
  fi

  rm -f "$PID_FILE"
  echo "daemon stopped"
}

status_daemon() {
  if is_running; then
    echo "running pid=$(cat "$PID_FILE")"
  else
    echo "stopped"
  fi
}

cmd="${1:-status}"
case "$cmd" in
  start-off)
    start_mode off
    ;;
  start-shadow)
    start_mode shadow
    ;;
  start-partial)
    start_mode partial "${2:-$ALLOWLIST_DEFAULT}"
    ;;
  start-on)
    start_mode on
    ;;
  rollback)
    # one-click rollback to batch-only: stop daemon
    stop_daemon
    echo "rollback complete: daemon disabled, system back to batch-only path"
    ;;
  stop)
    stop_daemon
    ;;
  status)
    status_daemon
    ;;
  *)
    cat <<USAGE
Usage:
  $0 start-off
  $0 start-shadow
  $0 start-partial [allowlist_file]
  $0 start-on
  $0 rollback   # one-click fallback to batch-only
  $0 stop
  $0 status
USAGE
    exit 2
    ;;
esac
