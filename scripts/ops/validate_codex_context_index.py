#!/usr/bin/env python3
"""Validate the bounded, non-authoritative Codex task context index."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CLASSES = {"orientation", "setup", "focused_test", "bounded_change", "verification"}
TASK_KEYS = {
    "id",
    "task_class",
    "authority_path",
    "context_paths",
    "test",
    "fixture_policy",
    "forbidden_scope",
}
TEST_KEYS = {"cwd", "argv"}
FIXTURE_KEYS = {"kind", "network", "secrets"}
FIXTURE_KINDS = {"recorded_fixture", "clean_cache", "local_fixture_only", "no_mutation"}
COMMANDS = {"bash", "git", "python3"}
CONTEXT_FILE_LIMIT = 4
CONTEXT_BYTE_LIMIT = 16_000
INDEX_BYTE_LIMIT = 8_000


class ContextIndexError(ValueError):
    """The index cannot support bounded retrieval."""


def fail(message: str) -> None:
    raise ContextIndexError(message)


def relative_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or any(char in value for char in "*?[]"):
        fail(f"{label} must be one concrete relative name")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\n" in value or "\r" in value:
        fail(f"{label} escapes repository")
    normalized = str(path)
    if normalized in {"", "."}:
        fail(f"{label} must name a repository entry")
    return normalized


def existing_file(value: object, label: str) -> Path:
    name = relative_name(value, label)
    path = ROOT / name
    if not path.is_file():
        fail(f"{label} does not exist: {name}")
    try:
        path.resolve(strict=True).relative_to(ROOT.resolve(strict=True))
    except ValueError:
        fail(f"{label} resolves outside repository: {name}")
    return path


def validate_test(task_class: str, test: object) -> None:
    if not isinstance(test, dict) or set(test) != TEST_KEYS:
        fail(f"{task_class}.test schema mismatch")
    if test["cwd"] != "TARGET_ROOT":
        fail(f"{task_class}.test.cwd must be TARGET_ROOT")
    argv = test["argv"]
    if not isinstance(argv, list) or not argv or len(argv) > 20:
        fail(f"{task_class}.test.argv must be bounded")
    if not all(isinstance(arg, str) and arg and "\n" not in arg for arg in argv):
        fail(f"{task_class}.test.argv contains an invalid argument")
    if any(any(char in arg for char in "*?[]") for arg in argv):
        fail(f"{task_class}.test.argv contains a wildcard")
    if argv[0] not in COMMANDS or shutil.which(argv[0]) is None:
        fail(f"{task_class}.test executable is unavailable")
    if any(any(control in arg for control in (";", "&&", "||", "|", "$(")) for arg in argv):
        fail(f"{task_class}.test contains shell control syntax")
    for arg in argv[1:]:
        if Path(arg).is_absolute():
            fail(f"{task_class}.test path must be repository-relative")
        if arg.startswith("-"):
            continue
        if arg.endswith((".json", ".md", ".py", ".sh")):
            existing_file(arg, f"{task_class}.test path")


def validate_fixture(task_class: str, fixture: object) -> None:
    if not isinstance(fixture, dict) or set(fixture) != FIXTURE_KEYS:
        fail(f"{task_class}.fixture_policy schema mismatch")
    if fixture["kind"] not in FIXTURE_KINDS:
        fail(f"{task_class}.fixture kind is invalid")
    if fixture["network"] is not False or fixture["secrets"] is not False:
        fail(f"{task_class}.fixture must deny network and secrets")


def validate_task(task: object, *, ids: set[str], authorities: set[str]) -> str:
    if not isinstance(task, dict) or set(task) != TASK_KEYS:
        fail("task schema mismatch")
    task_id = task["id"]
    task_class = task["task_class"]
    if not isinstance(task_id, str) or not task_id or task_id in ids:
        fail("duplicate or invalid task id")
    if task_class not in EXPECTED_CLASSES:
        fail("invalid task class")
    ids.add(task_id)

    authority = existing_file(task["authority_path"], f"{task_class}.authority_path")
    authority_name = str(authority.relative_to(ROOT))
    if authority_name in authorities:
        fail("duplicate authority path")
    authorities.add(authority_name)

    contexts = task["context_paths"]
    if (
        not isinstance(contexts, list)
        or not contexts
        or len(contexts) > CONTEXT_FILE_LIMIT
        or len(contexts) != len(set(contexts))
    ):
        fail(f"{task_class}.context_paths must be bounded and unique")
    context_files = [existing_file(item, f"{task_class}.context_path") for item in contexts]
    context_names = [str(path.relative_to(ROOT)) for path in context_files]
    if len(context_names) != len(set(context_names)):
        fail(f"{task_class}.context_paths contain a canonical duplicate")
    if authority_name not in set(context_names):
        fail(f"{task_class}.authority_path must be included in context_paths")
    if sum(path.stat().st_size for path in set(context_files)) > CONTEXT_BYTE_LIMIT:
        fail(f"{task_class} context budget exceeds {CONTEXT_BYTE_LIMIT} bytes")

    forbidden = task["forbidden_scope"]
    if not isinstance(forbidden, list) or not forbidden or len(forbidden) != len(set(forbidden)):
        fail(f"{task_class}.forbidden_scope must be a unique list")
    forbidden_names = {relative_name(item, f"{task_class}.forbidden_scope") for item in forbidden}
    if len(forbidden_names) != len(forbidden):
        fail(f"{task_class}.forbidden_scope contains a canonical duplicate")
    retrieval_names = {authority_name, *(str(path.relative_to(ROOT)) for path in context_files)}
    if forbidden_names & retrieval_names:
        fail(f"{task_class}.forbidden scope overlaps retrieval paths")

    validate_test(task_class, task["test"])
    validate_fixture(task_class, task["fixture_policy"])
    encoded = json.dumps(task, sort_keys=True).lower()
    if any(token in encoded for token in ("**", "full-corpus", "full corpus", "scan_all")):
        fail(f"{task_class} contains a broad fallback")
    return task_class


def validate(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > INDEX_BYTE_LIMIT:
            fail(f"index exceeds {INDEX_BYTE_LIMIT} bytes")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read JSON: {exc}")
    if not isinstance(data, dict) or set(data) != {"schema_version", "authority", "task_classes"}:
        fail("top-level schema mismatch")
    if data["schema_version"] != "codex-task-context-index-v1":
        fail("invalid schema identity")
    if data["authority"] != "non_authoritative_bounded_retrieval":
        fail("index cannot grant authority")
    tasks = data["task_classes"]
    if not isinstance(tasks, list) or len(tasks) != len(EXPECTED_CLASSES):
        fail("exactly five task classes are required")
    ids: set[str] = set()
    authorities: set[str] = set()
    classes = {validate_task(task, ids=ids, authorities=authorities) for task in tasks}
    if classes != EXPECTED_CLASSES:
        fail("task class coverage mismatch")
    return data


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_codex_context_index.py INDEX.json", file=sys.stderr)
        return 2
    try:
        validate(Path(argv[1]))
    except ContextIndexError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print("VALID: 5 bounded task classes; exact commands; no broad fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
