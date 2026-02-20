#!/usr/bin/env python3
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from memory_experience_v0_1 import _extract_memory_payload

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas"
FIXTURES_DIR = ROOT / "data" / "fixtures" / "critical-paths"

class ValidationError(Exception):
    pass

_schema_cache = {}


def load_schema(file_name: str):
    if file_name in _schema_cache:
        return _schema_cache[file_name]
    path = SCHEMAS_DIR / file_name
    data = json.loads(path.read_text())
    _schema_cache[file_name] = data
    return data


def is_type(value, t: str):
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


def check_datetime(s: str) -> bool:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        datetime.fromisoformat(s)
        return True
    except Exception:
        return False


def condition_matches(cond: dict, data) -> bool:
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


def validate(schema: dict, data, path: str, schema_file: str):
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("./"):
            raise ValidationError(f"{path}: unsupported ref {ref}")
        target = ref.split("/")[1]
        target_schema = load_schema(target)
        validate(target_schema, data, path, target)

    for part in schema.get("allOf", []):
        validate(part, data, path, schema_file)

    if "type" in schema and not is_type(data, schema["type"]):
        raise ValidationError(f"{path}: expected type {schema['type']}, got {type(data).__name__}")

    if "enum" in schema and data not in schema["enum"]:
        raise ValidationError(f"{path}: value {data!r} not in enum {schema['enum']}")

    if "const" in schema and data != schema["const"]:
        raise ValidationError(f"{path}: value {data!r} != const {schema['const']!r}")

    if isinstance(data, str):
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, data) is None:
            raise ValidationError(f"{path}: string does not match pattern {pattern}")
        if schema.get("format") == "date-time" and not check_datetime(data):
            raise ValidationError(f"{path}: invalid date-time {data!r}")

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            raise ValidationError(f"{path}: {data} < minimum {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            raise ValidationError(f"{path}: {data} > maximum {schema['maximum']}")

    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            raise ValidationError(f"{path}: length {len(data)} < minItems {schema['minItems']}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(data):
                validate(item_schema, item, f"{path}[{i}]", schema_file)

    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                raise ValidationError(f"{path}: missing required field {req}")

        props = schema.get("properties", {})
        for k, prop_schema in props.items():
            if k in data:
                validate(prop_schema, data[k], f"{path}.{k}", schema_file)

    if "if" in schema and "then" in schema:
        if condition_matches(schema["if"], data):
            validate(schema["then"], data, path, schema_file)


def validate_scenario_assertions(scenario: dict, source_path: Path):
    sid = scenario.get("scenario_id", "")

    if sid.startswith("S1"):
        assert scenario["cognition"]["epistemic_state"] == "supported", "S1 cognition must be supported"
        assert scenario["decision_trace"]["final_outcome"] in {"executed", "limited"}, "S1 outcome invalid"

    elif sid.startswith("S2"):
        assert scenario["memory"]["status"] == "rejected_poisoned", "S2 memory status must be rejected_poisoned"
        assert scenario["experience"]["status"] == "invalidated", "S2 experience must be invalidated"
        assert scenario["cognition"]["epistemic_state"] == "refuted", "S2 cognition must be refuted"
        assert any(e.get("event_type") == "rollback" for e in scenario.get("audit_events", [])), "S2 must include rollback event"

    elif sid.startswith("S3"):
        cg = scenario["cognition"]
        assert cg["status"] == "stale" and cg["epistemic_state"] == "uncertain", "S3 must enter stale+uncertain"
        assert cg.get("auto_verify_budget") == 0, "S3 budget must be exhausted"
        assert any(e.get("event_type") == "scheduler_job" for e in scenario.get("audit_events", [])), "S3 needs scheduler event"

    elif sid.startswith("S4"):
        dt = scenario["decision_trace"]
        assert dt["risk_tier"] == "high", "S4 must be high risk"
        assert dt["final_outcome"] != "executed", "S4 high-risk must not execute directly"
        assert dt["gates"]["risk_gate"] in {"block", "limit"}, "S4 risk gate invalid"

    elif sid.startswith("S5"):
        before = scenario["cognition_before"]
        after = scenario["cognition_after"]
        assert before["status"] == "stale" and before["epistemic_state"] == "uncertain", "S5 before state invalid"
        assert after["status"] == "active" and after["epistemic_state"] == "supported", "S5 after state invalid"

    elif sid.startswith("S6"):
        events = scenario.get("audit_events", [])
        assert len(events) >= 2, "S6 must include pull + retry events"
        assert any(e.get("after", {}).get("status") == "running" for e in events), "S6 missing running transition"
        assert any(
            e.get("after", {}).get("status") == "queued" and e.get("after", {}).get("attempt") == 1
            for e in events
        ), "S6 missing re-queue retry transition"

    elif sid.startswith("S7"):
        events = scenario.get("audit_events", [])
        assert len(events) >= 1, "S7 must include dead-letter event"
        assert any(e.get("after", {}).get("status") == "dead_letter" for e in events), "S7 must reach dead_letter"

    elif sid.startswith("S8"):
        mem = scenario["memory"]
        exp = scenario["experience"]
        assert mem["status"] == "active", "S8 memory should be active"
        assert exp["status"] == "candidate", "S8 experience should be candidate"
        assert mem["id"] in exp.get("memory_refs", []), "S8 experience must reference memory id"
        assert any(e.get("object_type") == "experience" for e in scenario.get("audit_events", [])), "S8 must include experience audit event"

    else:
        raise AssertionError(f"Unknown scenario id in {source_path.name}: {sid}")


def main():
    schema_map = {
        "memory": "memory.schema.json",
        "experience": "experience.schema.json",
        "cognition": "cognition.schema.json",
        "cognition_before": "cognition.schema.json",
        "cognition_after": "cognition.schema.json",
        "decision_trace": "decision-trace.schema.json",
    }

    files = sorted(FIXTURES_DIR.glob("*.json"))
    if not files:
        print("No scenario fixtures found.")
        return 1

    total = 0
    for fp in files:
        scenario = json.loads(fp.read_text())
        for key, schema_file in schema_map.items():
            if key in scenario:
                schema = load_schema(schema_file)
                validate(schema, scenario[key], f"{fp.name}.{key}", schema_file)
                total += 1

        if "audit_events" in scenario:
            audit_schema = load_schema("audit-event.schema.json")
            for i, ev in enumerate(scenario["audit_events"]):
                validate(audit_schema, ev, f"{fp.name}.audit_events[{i}]", "audit-event.schema.json")
                total += 1

        validate_scenario_assertions(scenario, fp)
        print(f"PASS {fp.name}")

    md_fixture = FIXTURES_DIR / "09-memory-markdown.md"
    if md_fixture.exists():
        md_memory = _extract_memory_payload(md_fixture)
        validate(load_schema("memory.schema.json"), md_memory, f"{md_fixture.name}.memory", "memory.schema.json")
        assert md_memory.get("content"), "S9 markdown memory must produce non-empty content"
        assert len(md_memory.get("evidence_refs", [])) >= 1, "S9 markdown memory must include evidence_refs"
        print(f"PASS {md_fixture.name}")
        total += 1

    print(f"All good. Validated objects/events: {total}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, AssertionError) as e:
        print(f"FAIL: {e}")
        raise SystemExit(1)
