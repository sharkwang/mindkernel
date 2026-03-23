"""API Key authentication for MindKernel REST API."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]
KEY_FILE = ROOT / ".mindkernel" / "api_key"

API_KEY_HEADER = APIKeyHeader(name="X-MindKernel-Key", auto_error=False)


def _load_key() -> str | None:
    """Load API key from file if it exists."""
    key_file = KEY_FILE.expanduser()
    if key_file.exists():
        return key_file.read_text().strip()
    return None


def _generate_key() -> str:
    """Generate a new random API key."""
    key = f"mk_{secrets.token_urlsafe(32)}"
    key_file = KEY_FILE.expanduser()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key)
    key_file.chmod(0o600)
    return key


def get_or_create_key() -> str:
    """Return existing key or generate a new one. Prints key on first gen."""
    key = _load_key()
    if key:
        return key
    new_key = _generate_key()
    print(f"[MindKernel API] New API key generated: {new_key}")
    print(f"[MindKernel API] Key saved to: {KEY_FILE.expanduser()}")
    return new_key


async def verify_api_key(key: str = Security(API_KEY_HEADER)) -> str:
    """Dependency: validate API key or raise 401."""
    if not key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-MindKernel-Key header. "
                   f"Run the API server once to generate a key.",
        )
    valid_key = get_or_create_key()
    if not secrets.compare_digest(key, valid_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key
