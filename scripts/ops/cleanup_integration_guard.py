#!/usr/bin/env python3
"""Fail-closed exact-head CAS and post-apply guard for bounded cleanup merges."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

GUARD_SCHEMA = "nexus.cleanup_integration_guard.v1"
MANIFEST_SCHEMA = "nexus.cleanup_integration_manifest.v1"
LIVE_SCHEMA = "nexus.cleanup_integration_live_snapshot.v1"
POST_SCHEMA = "nexus.cleanup_integration_post_snapshot.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GuardError(ValueError):
    """Raised when exact integration evidence is missing, stale, or inconsistent."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise GuardError(f"{field}: expected exact 40-character lowercase SHA")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise GuardError(f"{field}: expected non-empty string")
    return value


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise GuardError(f"{field}: expected positive integer")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GuardError(f"{field}: expected object")
    return value


def _sorted_unique_strings(value: object, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise GuardError(f"{field}: expected non-empty string list")
    items = tuple(value)
    if tuple(sorted(set(items))) != items:
        raise GuardError(f"{field}: must be sorted and unique")
    return items


def _required_checks(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list) or not value:
        raise GuardError("required_checks: expected non-empty list")
    rows: list[tuple[str, int]] = []
    for index, raw in enumerate(value):
        row = _mapping(raw, f"required_checks[{index}]")
        context = _string(row.get("context"), f"required_checks[{index}].context")
        integration_id = _integer(
            row.get("integration_id"), f"required_checks[{index}].integration_id"
        )
        rows.append((context, integration_id))
    if tuple(sorted(set(rows))) != tuple(rows):
        raise GuardError("required_checks: must be sorted and unique")
    return tuple(rows)


def validate_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    if raw.get("schema") != MANIFEST_SCHEMA:
        raise GuardError("manifest.schema: unsupported schema")
    repository = _string(raw.get("repository"), "manifest.repository")
    pr_number = _integer(raw.get("pr_number"), "manifest.pr_number")
    base_ref = _string(raw.get("base_ref"), "manifest.base_ref")
    base_sha = _exact_sha(raw.get("base_sha"), "manifest.base_sha")
    head_sha = _exact_sha(raw.get("head_sha"), "manifest.head_sha")
    head_tree = _exact_sha(raw.get("head_tree"), "manifest.head_tree")
    changed_paths = _sorted_unique_strings(raw.get("changed_paths"), "manifest.changed_paths")
    deleted_paths = _sorted_unique_strings(raw.get("deleted_paths"), "manifest.deleted_paths")
    if not set(deleted_paths).issubset(changed_paths):
        raise GuardError("manifest.deleted_paths: must be a subset of changed_paths")
    checks = _required_checks(raw.get("required_checks"))
    return {
        "schema": MANIFEST_SCHEMA,
        "repository": repository,
        "pr_number": pr_number,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "head_tree": head_tree,
        "changed_paths": list(changed_paths),
        "deleted_paths": list(deleted_paths),
        "required_checks": [
            {"context": context, "integration_id": integration_id}
            for context, integration_id in checks
        ],
    }


def _validate_live_snapshot(
    raw: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    if raw.get("schema") != LIVE_SCHEMA:
        raise GuardError("snapshot.schema: unsupported schema")
    for field in ("repository", "base_ref"):
        actual = _string(raw.get(field), f"snapshot.{field}")
        if actual != manifest[field]:
            raise GuardError(f"snapshot.{field}: contract drift")
    if _integer(raw.get("pr_number"), "snapshot.pr_number") != manifest["pr_number"]:
        raise GuardError("snapshot.pr_number: contract drift")
    for field in ("base_sha", "head_sha", "head_tree"):
        actual = _exact_sha(raw.get(field), f"snapshot.{field}")
        if actual != manifest[field]:
            raise GuardError(f"snapshot.{field}: stale or drifted")
    if raw.get("pr_state") != "open":
        raise GuardError("snapshot.pr_state: PR must still be open")
    if raw.get("draft") is not False:
        raise GuardError("snapshot.draft: PR must not be draft")
    if raw.get("mergeable") is not True:
        raise GuardError("snapshot.mergeable: PR must be mergeable")
    if raw.get("target_clean") is not True:
        raise GuardError("snapshot.target_clean: target must be clean")

    required = {
        (row["context"], row["integration_id"])
        for row in manifest["required_checks"]
    }
    checks_raw = raw.get("checks")
    if not isinstance(checks_raw, list):
        raise GuardError("snapshot.checks: expected list")
    seen: set[tuple[str, int]] = set()
    normalized_checks: list[dict[str, Any]] = []
    for index, value in enumerate(checks_raw):
        row = _mapping(value, f"snapshot.checks[{index}]")
        context = _string(row.get("context"), f"snapshot.checks[{index}].context")
        integration_id = _integer(
            row.get("integration_id"), f"snapshot.checks[{index}].integration_id"
        )
        key = (context, integration_id)
        if key not in required:
            continue
        if key in seen:
            raise GuardError(f"snapshot.checks: duplicate required check {context}")
        if _exact_sha(row.get("head_sha"), f"snapshot.checks[{index}].head_sha") != manifest[
            "head_sha"
        ]:
            raise GuardError(f"snapshot.checks[{index}]: stale check head")
        if row.get("status") != "completed" or row.get("conclusion") != "success":
            raise GuardError(f"snapshot.checks[{index}]: required check not successful")
        seen.add(key)
        normalized_checks.append(
            {
                "context": context,
                "integration_id": integration_id,
                "head_sha": manifest["head_sha"],
                "status": "completed",
                "conclusion": "success",
            }
        )
    missing = sorted(required - seen)
    if missing:
        raise GuardError(f"snapshot.checks: missing required checks {missing!r}")
    normalized_checks.sort(key=lambda row: (row["context"], row["integration_id"]))
    return {
        "schema": LIVE_SCHEMA,
        "repository": manifest["repository"],
        "pr_number": manifest["pr_number"],
        "base_ref": manifest["base_ref"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "head_tree": manifest["head_tree"],
        "pr_state": "open",
        "draft": False,
        "mergeable": True,
        "target_clean": True,
        "checks": normalized_checks,
    }


def preflight(
    manifest_raw: Mapping[str, Any], snapshot_raw: Mapping[str, Any], *, dry_run: bool
) -> dict[str, Any]:
    manifest = validate_manifest(manifest_raw)
    snapshot = _validate_live_snapshot(snapshot_raw, manifest)
    manifest_sha256 = _sha256(manifest)
    snapshot_sha256 = _sha256(snapshot)
    cas_binding = {
        "repository": manifest["repository"],
        "pr_number": manifest["pr_number"],
        "base_ref": manifest["base_ref"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "head_tree": manifest["head_tree"],
        "manifest_sha256": manifest_sha256,
        "snapshot_sha256": snapshot_sha256,
    }
    return {
        "schema": GUARD_SCHEMA,
        "phase": "preflight",
        "status": "PASS",
        "dry_run": dry_run,
        **cas_binding,
        "cas_token": _sha256(cas_binding),
        "changed_paths": manifest["changed_paths"],
        "deleted_paths": manifest["deleted_paths"],
        "required_checks": snapshot["checks"],
    }


def post_apply(
    manifest_raw: Mapping[str, Any],
    preflight_raw: Mapping[str, Any],
    snapshot_raw: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = validate_manifest(manifest_raw)
    preflight_receipt = _mapping(preflight_raw, "preflight")
    if preflight_receipt.get("schema") != GUARD_SCHEMA:
        raise GuardError("preflight.schema: unsupported schema")
    if preflight_receipt.get("phase") != "preflight" or preflight_receipt.get("status") != "PASS":
        raise GuardError("preflight: missing PASS receipt")
    if preflight_receipt.get("dry_run") is not False:
        raise GuardError("preflight: dry-run receipt cannot authorize post-apply verification")
    expected_manifest_sha = _sha256(manifest)
    if preflight_receipt.get("manifest_sha256") != expected_manifest_sha:
        raise GuardError("preflight: manifest binding drift")
    for field in ("repository", "pr_number", "base_ref", "base_sha", "head_sha", "head_tree"):
        if preflight_receipt.get(field) != manifest[field]:
            raise GuardError(f"preflight.{field}: binding drift")

    reconstructed_live = {
        "schema": LIVE_SCHEMA,
        "repository": manifest["repository"],
        "pr_number": manifest["pr_number"],
        "base_ref": manifest["base_ref"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "head_tree": manifest["head_tree"],
        "pr_state": "open",
        "draft": False,
        "mergeable": True,
        "target_clean": True,
        "checks": preflight_receipt.get("required_checks"),
    }
    normalized_live = _validate_live_snapshot(reconstructed_live, manifest)
    expected_snapshot_sha = _sha256(normalized_live)
    if preflight_receipt.get("snapshot_sha256") != expected_snapshot_sha:
        raise GuardError("preflight: snapshot binding drift")
    expected_cas_binding = {
        "repository": manifest["repository"],
        "pr_number": manifest["pr_number"],
        "base_ref": manifest["base_ref"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "head_tree": manifest["head_tree"],
        "manifest_sha256": expected_manifest_sha,
        "snapshot_sha256": expected_snapshot_sha,
    }
    if preflight_receipt.get("cas_token") != _sha256(expected_cas_binding):
        raise GuardError("preflight: CAS token binding drift")

    snapshot = _mapping(snapshot_raw, "post_snapshot")
    if snapshot.get("schema") != POST_SCHEMA:
        raise GuardError("post_snapshot.schema: unsupported schema")
    if snapshot.get("repository") != manifest["repository"]:
        raise GuardError("post_snapshot.repository: contract drift")
    if snapshot.get("pr_number") != manifest["pr_number"]:
        raise GuardError("post_snapshot.pr_number: contract drift")
    if snapshot.get("base_ref") != manifest["base_ref"]:
        raise GuardError("post_snapshot.base_ref: contract drift")
    if snapshot.get("cas_token") != preflight_receipt.get("cas_token"):
        raise GuardError("post_snapshot.cas_token: replay or binding drift")
    if snapshot.get("manifest_sha256") != expected_manifest_sha:
        raise GuardError("post_snapshot.manifest_sha256: changed manifest")

    merge_sha = _exact_sha(snapshot.get("merge_sha"), "post_snapshot.merge_sha")
    merge_tree = _exact_sha(snapshot.get("merge_tree"), "post_snapshot.merge_tree")
    if merge_tree != manifest["head_tree"]:
        raise GuardError("post_snapshot.merge_tree: resulting tree differs from approved head tree")
    current_main_sha = _exact_sha(
        snapshot.get("current_base_sha"), "post_snapshot.current_base_sha"
    )
    if current_main_sha != merge_sha:
        raise GuardError("post_snapshot.current_base_sha: target moved after apply")
    parents = snapshot.get("parents")
    if not isinstance(parents, list) or parents != [manifest["base_sha"], manifest["head_sha"]]:
        raise GuardError("post_snapshot.parents: concurrent base/head drift or non-exact merge")

    changed_paths = _sorted_unique_strings(
        snapshot.get("changed_paths"), "post_snapshot.changed_paths"
    )
    if list(changed_paths) != manifest["changed_paths"]:
        raise GuardError("post_snapshot.changed_paths: physical diff drift")
    path_states = _mapping(snapshot.get("path_states"), "post_snapshot.path_states")
    expected_deleted = set(manifest["deleted_paths"])
    if set(path_states) != expected_deleted:
        raise GuardError("post_snapshot.path_states: incomplete deleted-path audit")
    still_present = sorted(path for path in expected_deleted if path_states.get(path) is not False)
    if still_present:
        raise GuardError(f"post_snapshot.path_states: deleted paths still present {still_present!r}")

    post_check_snapshot = {
        "schema": LIVE_SCHEMA,
        "repository": manifest["repository"],
        "pr_number": manifest["pr_number"],
        "base_ref": manifest["base_ref"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "head_tree": manifest["head_tree"],
        "pr_state": "open",
        "draft": False,
        "mergeable": True,
        "target_clean": True,
        "checks": snapshot.get("checks"),
    }
    post_checks = _validate_live_snapshot(post_check_snapshot, manifest)["checks"]
    if post_checks != normalized_live["checks"]:
        raise GuardError("post_snapshot.checks: required check receipt drift")

    return {
        "schema": GUARD_SCHEMA,
        "phase": "post_apply",
        "status": "PASS",
        "repository": manifest["repository"],
        "pr_number": manifest["pr_number"],
        "base_ref": manifest["base_ref"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "head_tree": manifest["head_tree"],
        "merge_sha": merge_sha,
        "merge_tree": merge_tree,
        "manifest_sha256": expected_manifest_sha,
        "cas_token": preflight_receipt["cas_token"],
        "changed_paths": manifest["changed_paths"],
        "deleted_paths": manifest["deleted_paths"],
        "required_checks": post_checks,
        "post_snapshot_sha256": _sha256(dict(snapshot)),
    }


def _json_argument(value: str, field: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise GuardError(f"{field}: invalid JSON") from exc
    return _mapping(parsed, field)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pre = subparsers.add_parser("preflight")
    pre.add_argument("--manifest-json", required=True)
    pre.add_argument("--snapshot-json", required=True)
    pre.add_argument("--dry-run", action="store_true")
    post = subparsers.add_parser("post-apply")
    post.add_argument("--manifest-json", required=True)
    post.add_argument("--preflight-receipt-json", required=True)
    post.add_argument("--snapshot-json", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = _json_argument(args.manifest_json, "manifest")
        snapshot = _json_argument(args.snapshot_json, "snapshot")
        if args.command == "preflight":
            receipt = preflight(manifest, snapshot, dry_run=args.dry_run)
        else:
            receipt = post_apply(
                manifest,
                _json_argument(args.preflight_receipt_json, "preflight"),
                snapshot,
            )
    except GuardError as exc:
        print(json.dumps({"schema": GUARD_SCHEMA, "status": "BLOCKED", "reason": str(exc)}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
