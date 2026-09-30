#!/usr/bin/env python3
"""Read-only provider for canonical governed GitHub orchestration evidence."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.orchestrator.github_orchestration import (  # noqa: E402
    build_governed_orchestration_evidence,
    governed_evidence_task_card_path,
)


def _gh_json(endpoint: str, *fields: tuple[str, str]) -> Any:
    command = ["gh", "api", "--method", "GET", endpoint]
    for key, value in fields:
        command.extend(["-f", f"{key}={value}"])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _artifact_member(repository: str, artifact_id: int, member_name: str) -> bytes:
    endpoint = f"repos/{repository}/actions/artifacts/{artifact_id}/zip"
    with tempfile.TemporaryFile() as archive_file:
        subprocess.run(
            ["gh", "api", "--method", "GET", endpoint],
            check=True,
            stdout=archive_file,
            stderr=subprocess.PIPE,
        )
        archive_file.seek(0)
        with zipfile.ZipFile(archive_file) as archive:
            names = [name for name in archive.namelist() if Path(name).name == member_name]
            if len(names) != 1:
                raise ValueError(
                    f"ARTIFACT_MEMBER_{member_name.upper().replace('-', '_')}_UNPROVEN"
                )
            return archive.read(names[0])


def _content_bytes(repository: str, path: str, ref: str) -> bytes:
    encoded_path = quote(path, safe="/")
    payload = _gh_json(
        f"repos/{repository}/contents/{encoded_path}",
        ("ref", ref),
    )
    if not isinstance(payload, dict) or payload.get("encoding") != "base64":
        raise ValueError("TASK_CARD_IDENTITY_MISSING")
    try:
        return base64.b64decode(str(payload["content"]), validate=False)
    except (KeyError, ValueError) as exc:
        raise ValueError("TASK_CARD_IDENTITY_MISSING") from exc


def _required_check_names(repository: str) -> tuple[str, ...]:
    summaries = _gh_json(f"repos/{repository}/rulesets")
    if not isinstance(summaries, list):
        raise ValueError("REQUIRED_CHECK_STATE_UNPROVEN")
    names: set[str] = set()
    for summary in summaries:
        if not isinstance(summary, dict) or summary.get("enforcement") != "active":
            continue
        ruleset_id = summary.get("id")
        if not isinstance(ruleset_id, int):
            continue
        detail = _gh_json(f"repos/{repository}/rulesets/{ruleset_id}")
        rules = detail.get("rules", ()) if isinstance(detail, dict) else ()
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
                continue
            params = rule.get("parameters") or {}
            for item in params.get("required_status_checks") or ():
                if isinstance(item, dict) and isinstance(item.get("context"), str):
                    names.add(item["context"])
    if not names:
        raise ValueError("REQUIRED_CHECK_STATE_UNPROVEN")
    return tuple(sorted(names))


def _latest_check_observations(repository: str, head_sha: str) -> tuple[dict[str, Any], ...]:
    payload = _gh_json(
        f"repos/{repository}/commits/{head_sha}/check-runs",
        ("per_page", "100"),
    )
    runs = payload.get("check_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise ValueError("REQUIRED_CHECK_STATE_UNPROVEN")
    latest: dict[str, dict[str, Any]] = {}
    for item in runs:
        if not isinstance(item, dict) or item.get("head_sha") != head_sha:
            continue
        name = item.get("name")
        run_id = item.get("id")
        if not isinstance(name, str) or not isinstance(run_id, int):
            continue
        previous = latest.get(name)
        if previous is None or run_id > int(previous["id"]):
            latest[name] = item
    return tuple(
        {
            "id": item["id"],
            "name": name,
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
            "head_sha": item.get("head_sha"),
            "details_url": item.get("details_url"),
        }
        for name, item in sorted(latest.items())
    )


def _trusted_run_id(checks: tuple[dict[str, Any], ...]) -> int:
    ids: set[int] = set()
    trusted_names = {
        "Trusted controller (default branch)",
        "Trusted verifier (default branch)",
    }
    for item in checks:
        if item["name"] not in trusted_names:
            continue
        match = re.search(r"/actions/runs/(\d+)(?:/|$)", str(item.get("details_url") or ""))
        if match:
            ids.add(int(match.group(1)))
    if len(ids) != 1:
        raise ValueError("CANDIDATE_PROVENANCE_MISSING")
    return next(iter(ids))


def _trusted_artifact_ids(repository: str, run_id: int) -> tuple[int, int]:
    payload = _gh_json(
        f"repos/{repository}/actions/runs/{run_id}/artifacts",
        ("per_page", "100"),
    )
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, list):
        raise ValueError("CANDIDATE_PROVENANCE_MISSING")
    controller = [
        item
        for item in artifacts
        if isinstance(item, dict)
        and not item.get("expired")
        and str(item.get("name", "")).startswith("trusted-anchor-controller-")
    ]
    verifier = [
        item
        for item in artifacts
        if isinstance(item, dict)
        and not item.get("expired")
        and str(item.get("name", "")).startswith("trusted-anchor-executor-")
    ]
    if len(controller) != 1 or len(verifier) != 1:
        raise ValueError("CANDIDATE_PROVENANCE_MISSING")
    return int(controller[0]["id"]), int(verifier[0]["id"])


def _impact_artifact_id(repository: str, head_sha: str) -> int:
    name = f"exact-base-impact-{head_sha}"
    payload = _gh_json(
        f"repos/{repository}/actions/artifacts",
        ("name", name),
        ("per_page", "100"),
    )
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    candidates = []
    for item in artifacts or ():
        if not isinstance(item, dict) or item.get("expired") or item.get("name") != name:
            continue
        workflow = item.get("workflow_run") or {}
        if workflow.get("head_sha") in {None, head_sha}:
            candidates.append(item)
    if len(candidates) != 1:
        raise ValueError("IMPACT_EVIDENCE_UNPROVEN")
    return int(candidates[0]["id"])


def collect_from_github(
    *,
    repository: str,
    issue_number: int,
    pull_request_number: int,
    acceptance_comment_id: int,
    implementer: str,
    freshness_minutes: int = 15,
):
    pr = _gh_json(f"repos/{repository}/pulls/{pull_request_number}")
    if not isinstance(pr, dict):
        raise ValueError("SUBJECT_IDENTITY_MISMATCH")
    body = pr.get("body")
    head_sha = (pr.get("head") or {}).get("sha")
    if not isinstance(body, str) or not isinstance(head_sha, str):
        raise ValueError("SUBJECT_IDENTITY_MISMATCH")

    card_path = governed_evidence_task_card_path(body)
    card_bytes = _content_bytes(repository, card_path, head_sha)
    checks = _latest_check_observations(repository, head_sha)
    run_id = _trusted_run_id(checks)
    controller_id, verifier_id = _trusted_artifact_ids(repository, run_id)
    controller_bytes = _artifact_member(repository, controller_id, "manifest.json")
    verifier_bytes = _artifact_member(repository, verifier_id, "raw-evidence.json")

    impact_id = _impact_artifact_id(repository, head_sha)
    impact_plan = json.loads(_artifact_member(repository, impact_id, "plan.json"))
    impact_classification = json.loads(
        _artifact_member(repository, impact_id, "classification.json")
    )

    acceptance = _gh_json(f"repos/{repository}/issues/comments/{acceptance_comment_id}")
    comment_author = (acceptance.get("user") or {}).get("login")
    comment_body = acceptance.get("body")
    if not isinstance(comment_author, str) or not isinstance(comment_body, str):
        raise ValueError("INDEPENDENT_ACCEPTANCE_MISSING")

    now = datetime.now(timezone.utc)
    return build_governed_orchestration_evidence(
        repository=repository,
        issue_number=issue_number,
        pull_request_number=pull_request_number,
        pr_body=body,
        task_card_path=card_path,
        task_card_bytes=card_bytes,
        controller_manifest_bytes=controller_bytes,
        verifier_evidence_bytes=verifier_bytes,
        acceptance_comment_id=acceptance_comment_id,
        acceptance_comment_author=comment_author,
        acceptance_comment_body=comment_body,
        required_check_names=_required_check_names(repository),
        check_observations=checks,
        impact_plan=impact_plan,
        impact_classification=impact_classification,
        implementer=implementer,
        observed_at=now,
        fresh_until=now + timedelta(minutes=freshness_minutes),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project authoritative governed GitHub evidence into the current v2 contract."
    )
    parser.add_argument("--repository", default="James3014/Nexus-new")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--acceptance-comment", type=int, required=True)
    parser.add_argument("--implementer", required=True)
    parser.add_argument("--freshness-minutes", type=int, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = collect_from_github(
        repository=args.repository,
        issue_number=args.issue,
        pull_request_number=args.pr,
        acceptance_comment_id=args.acceptance_comment,
        implementer=args.implementer,
        freshness_minutes=args.freshness_minutes,
    )
    rendered = json.dumps(evidence.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
