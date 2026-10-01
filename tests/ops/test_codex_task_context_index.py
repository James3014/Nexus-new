import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.validate_codex_context_index import (
    CONTEXT_BYTE_LIMIT,
    EXPECTED_CLASSES,
    ContextIndexError,
    validate,
)

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "configs/codex_task_context_index.json"
VALIDATOR = ROOT / "scripts/ops/validate_codex_context_index.py"


def canonical() -> dict:
    return json.loads(INDEX.read_text())


def candidate(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "index.json"
    path.write_text(json.dumps(data))
    return path


def test_canonical_index_is_valid_complete_and_bounded():
    data = validate(INDEX)
    assert {task["task_class"] for task in data["task_classes"]} == EXPECTED_CLASSES
    assert INDEX.stat().st_size <= 8_000
    for task in data["task_classes"]:
        context_bytes = sum((ROOT / name).stat().st_size for name in task["context_paths"])
        assert context_bytes <= CONTEXT_BYTE_LIMIT


def test_cli_emits_bounded_summary():
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(INDEX)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert (
        result.stdout.strip() == "VALID: 5 bounded task classes; exact commands; no broad fallback"
    )


@pytest.mark.parametrize("field", ["authority_path", "context_paths"])
def test_missing_mapping_path_fails_closed(tmp_path, field):
    data = canonical()
    data["task_classes"][0][field] = (
        "does/not/exist" if field == "authority_path" else ["does/not/exist"]
    )
    with pytest.raises(ContextIndexError, match="does not exist"):
        validate(candidate(tmp_path, data))


def test_duplicate_authority_and_broad_fallback_fail_closed(tmp_path):
    data = canonical()
    data["task_classes"][1]["authority_path"] = data["task_classes"][0]["authority_path"]
    with pytest.raises(ContextIndexError, match="duplicate authority"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["context_paths"].append("**/*")
    with pytest.raises(ContextIndexError, match="concrete relative"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["context_paths"].append("./AGENTS.md")
    with pytest.raises(ContextIndexError, match="canonical duplicate"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["forbidden_scope"].append("./.env")
    with pytest.raises(ContextIndexError, match="canonical duplicate"):
        validate(candidate(tmp_path, data))


def test_unknown_decision_field_and_forbidden_overlap_fail_closed(tmp_path):
    data = canonical()
    data["task_classes"][0]["provider"] = "example"
    with pytest.raises(ContextIndexError, match="task schema"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["forbidden_scope"].append(data["task_classes"][0]["context_paths"][0])
    with pytest.raises(ContextIndexError, match="overlaps"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["context_paths"].remove(data["task_classes"][0]["authority_path"])
    with pytest.raises(ContextIndexError, match="included in context_paths"):
        validate(candidate(tmp_path, data))


def test_command_fixture_and_context_budget_fail_closed(tmp_path):
    data = canonical()
    data["task_classes"][0]["test"]["argv"][0] = "missing-executable"
    with pytest.raises(ContextIndexError, match="executable"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["test"]["argv"].append("tests/**")
    with pytest.raises(ContextIndexError, match="wildcard"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["test"]["argv"].append("value;echo unsafe")
    with pytest.raises(ContextIndexError, match="shell control"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][0]["test"]["argv"].append("/tmp/does-not-exist.py")
    with pytest.raises(ContextIndexError, match="repository-relative"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][2]["fixture_policy"]["secrets"] = True
    with pytest.raises(ContextIndexError, match="deny network and secrets"):
        validate(candidate(tmp_path, data))

    data = canonical()
    data["task_classes"][2]["context_paths"] = [
        data["task_classes"][2]["authority_path"],
        "scripts/engine/nexus_cli.py",
    ]
    with pytest.raises(ContextIndexError, match="context budget"):
        validate(candidate(tmp_path, data))


def test_duplicate_task_class_is_not_hidden_by_set_comprehension(tmp_path):
    data = canonical()
    data["task_classes"][1]["task_class"] = data["task_classes"][0]["task_class"]
    with pytest.raises(ContextIndexError, match="coverage mismatch"):
        validate(candidate(tmp_path, copy.deepcopy(data)))
