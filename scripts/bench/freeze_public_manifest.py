#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.bench.capability_ab_runner import _sha256_text


REQUIRED_TASK_KEYS = {
    "id",
    "category",
    "difficulty",
    "repo_kind",
    "repo",
    "repo_ref",
    "task_desc",
    "success_criteria",
    "mutation_required",
    "allowed_files",
    "forbidden_files",
    "setup_command",
    "verification_command",
}
PUBLIC_CATEGORIES = {"bugfix", "test_repair", "refactor", "feature", "docs_code_sync", "ops_research"}
PUBLIC_REPO_KINDS = {"nexus_internal", "neutral_fixture", "external"}
PLACEHOLDER_MARKERS = {"pinned-before-freeze", "placeholder", "todo", "tbd"}


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload, _sha256_text(text)


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in PLACEHOLDER_MARKERS)
    if isinstance(value, list):
        return any(_has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_has_placeholder(item) for item in value.values())
    return False


def validate_manifest(path: str | Path, *, repo_root: str | Path | None = None, allow_unfrozen: bool = False) -> dict[str, Any]:
    manifest_path = Path(path)
    root = Path(repo_root) if repo_root is not None else manifest_path.resolve().parents[2]
    payload, manifest_hash = _load_manifest(manifest_path)
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("manifest.tasks must be a non-empty list")
    if payload.get("frozen") is not True and not allow_unfrozen:
        raise ValueError("manifest must set frozen=true before freeze receipt generation")

    ids: set[str] = set()
    duplicate_ids: list[str] = []
    categories: Counter[str] = Counter()
    repo_kinds: Counter[str] = Counter()
    unresolved: list[str] = []
    errors: list[str] = []

    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"task[{index}] must be an object")
            continue
        missing = sorted(REQUIRED_TASK_KEYS - set(task))
        if missing:
            errors.append(f"{task.get('id', f'task[{index}]')} missing keys: {', '.join(missing)}")
            continue
        task_id = str(task["id"])
        if task_id in ids:
            duplicate_ids.append(task_id)
        ids.add(task_id)

        category = str(task["category"])
        repo_kind = str(task["repo_kind"])
        if category not in PUBLIC_CATEGORIES:
            errors.append(f"{task_id} invalid category: {category}")
        if repo_kind not in PUBLIC_REPO_KINDS:
            errors.append(f"{task_id} invalid repo_kind: {repo_kind}")
        if task.get("success_criteria") != "patch_and_tests_pass":
            errors.append(f"{task_id} success_criteria must be patch_and_tests_pass")
        if task.get("mutation_required") is not True:
            errors.append(f"{task_id} mutation_required must be true")
        if not task.get("allowed_files"):
            errors.append(f"{task_id} allowed_files must be non-empty")
        if not task.get("forbidden_files"):
            errors.append(f"{task_id} forbidden_files must be non-empty")
        if _has_placeholder(task):
            unresolved.append(task_id)
        if repo_kind == "nexus_internal":
            target_file = task.get("target_file")
            test_file = task.get("test_file")
            if not target_file or not (root / str(target_file)).exists():
                errors.append(f"{task_id} nexus_internal target_file missing: {target_file}")
            if not test_file or not (root / str(test_file)).exists():
                errors.append(f"{task_id} nexus_internal test_file missing: {test_file}")
        if repo_kind == "neutral_fixture" and not task.get("fixture_kind"):
            errors.append(f"{task_id} neutral_fixture requires fixture_kind")
        if repo_kind == "external":
            repo_ref = str(task.get("repo_ref", ""))
            if not task.get("repo", "").startswith("https://"):
                errors.append(f"{task_id} external repo must be https URL")
            if len(repo_ref) < 12 or repo_ref == "pinned-before-freeze":
                errors.append(f"{task_id} external repo_ref must be pinned commit SHA")

        categories[category] += 1
        repo_kinds[repo_kind] += 1

    if duplicate_ids:
        errors.append("duplicate task ids: " + ", ".join(sorted(set(duplicate_ids))))
    if unresolved:
        errors.append("unresolved placeholder tasks: " + ", ".join(unresolved))
    if errors:
        raise ValueError("manifest freeze validation failed:\n- " + "\n- ".join(errors))

    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_hash,
        "task_count": len(tasks),
        "category_counts": dict(sorted(categories.items())),
        "repo_kind_counts": dict(sorted(repo_kinds.items())),
    }


def build_freeze_receipt(path: str | Path, *, repo_root: str | Path | None = None, allow_unfrozen: bool = False) -> dict[str, Any]:
    summary = validate_manifest(path, repo_root=repo_root, allow_unfrozen=allow_unfrozen)
    return {
        "schema": "nexus_public_benchmark_freeze_receipt_v1",
        "status": "VERIFIED",
        "frozen_at_unix": int(time.time()),
        **summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and freeze a Nexus public benchmark manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--output-file", default="")
    parser.add_argument("--allow-unfrozen", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    receipt = build_freeze_receipt(
        args.manifest,
        repo_root=args.repo_root or None,
        allow_unfrozen=bool(args.allow_unfrozen),
    )
    if args.output_file:
        out = Path(args.output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.output_json or not args.output_file:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
