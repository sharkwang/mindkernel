#!/usr/bin/env python3
"""Lightweight JSON Schema runtime validator (subset used by MindKernel v0.1)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas"


class SchemaValidationError(ValueError):
    pass


_schema_cache: dict[str, dict] = {}


def load_schema(file_name: str) -> dict:
    if file_name in _schema_cache:
        return _schema_cache[file_name]
    path = SCHEMAS_DIR / file_name
    data = json.loads(path.read_text())
    _schema_cache[file_name] = data
    return data


def _is_type(value, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    return True


def _is_datetime(s: str) -> bool:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        datetime.fromisoformat(s)
        return True
    except Exception:
        return False


def _condition_matches(cond: dict, data) -> bool:
    if not isinstance(data, dict):
        return False

    for key in cond.get("required", []):
        if key not in data:
            return False

    for prop, rule in cond.get("properties", {}).items():
        if prop not in data:
            continue
        val = data[prop]
        if "const" in rule and val != rule["const"]:
            return False
        if "enum" in rule and val not in rule["enum"]:
            return False
    return True


def validate(schema: dict, data, path: str = "$"):
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("./"):
            raise SchemaValidationError(f"{path}: unsupported ref {ref}")
        target = ref.split("/")[1]
        validate(load_schema(target), data, path)

    for part in schema.get("allOf", []):
        validate(part, data, path)

    if "type" in schema and not _is_type(data, schema["type"]):
        raise SchemaValidationError(f"{path}: expected type {schema['type']}, got {type(data).__name__}")

    if "enum" in schema and data not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value {data!r} not in enum {schema['enum']}")

    if "const" in schema and data != schema["const"]:
        raise SchemaValidationError(f"{path}: value {data!r} != const {schema['const']!r}")

    if isinstance(data, str):
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, data) is None:
            raise SchemaValidationError(f"{path}: string does not match pattern {pattern}")
        if schema.get("format") == "date-time" and not _is_datetime(data):
            raise SchemaValidationError(f"{path}: invalid date-time {data!r}")

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            raise SchemaValidationError(f"{path}: {data} < minimum {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            raise SchemaValidationError(f"{path}: {data} > maximum {schema['maximum']}")

    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            raise SchemaValidationError(f"{path}: length {len(data)} < minItems {schema['minItems']}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(data):
                validate(item_schema, item, f"{path}[{i}]")

    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                raise SchemaValidationError(f"{path}: missing required field {req}")

        props = schema.get("properties", {})
        for k, prop_schema in props.items():
            if k in data:
                validate(prop_schema, data[k], f"{path}.{k}")

    if "if" in schema and "then" in schema:
        if _condition_matches(schema["if"], data):
            validate(schema["then"], data, path)


def validate_payload(schema_file: str, payload: dict):
    validate(load_schema(schema_file), payload, "$")
