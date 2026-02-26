#!/usr/bin/env bash
set -euo pipefail

# MindKernel bootstrap installer (local/dev)
# Usage:
#   ./scripts/install.sh
#   ./scripts/install.sh --verify

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERIFY=0

for arg in "$@"; do
  case "$arg" in
    --verify)
      VERIFY=1
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: ./scripts/install.sh [--verify]"
      exit 2
      ;;
  esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[install] python3 not found. Please install Python 3.11+ first."
  exit 1
fi

PY_VER="$($PYTHON_BIN - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

PY_MAJ="${PY_VER%%.*}"
PY_MIN="${PY_VER##*.}"
if [[ "$PY_MAJ" -lt 3 ]] || [[ "$PY_MAJ" -eq 3 && "$PY_MIN" -lt 11 ]]; then
  echo "[install] Python >= 3.11 required, current: ${PY_VER}"
  exit 1
fi

echo "[install] repo: ${ROOT_DIR}"
echo "[install] python: ${PY_VER} (${PYTHON_BIN})"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[install] creating virtualenv at .venv"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "[install] virtualenv already exists at .venv"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel >/dev/null

if [[ -f "${ROOT_DIR}/requirements.txt" ]]; then
  echo "[install] installing requirements.txt"
  pip install -r "${ROOT_DIR}/requirements.txt"
else
  echo "[install] no requirements.txt detected (project is stdlib-first)."
fi

if [[ "$VERIFY" -eq 1 ]]; then
  echo "[verify] running release quick gate (may take ~1-2 minutes)..."
  python "${ROOT_DIR}/tools/release/release_check_v0_1.py" --quick --release-target install-verify
  echo "[verify] done"
fi

echo ""
echo "✅ MindKernel install complete"
echo "Next:"
echo "  source .venv/bin/activate"
echo "  python3 tools/release/release_check_v0_1.py --quick --release-target local-dev"
