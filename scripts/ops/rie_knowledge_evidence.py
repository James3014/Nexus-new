#!/usr/bin/env python3
"""RIE knowledge applicability -> advisory codeintel evidence artifact (#1579).

Builds ``changes[]`` and ``observed_source_sha256`` from git plus the
owner-declared manifest ``docs/knowledge/rie_knowledge_manifest.v1.json`` and
calls ``nexus.services.rie_knowledge_applicability`` (which invokes the pinned
RIE engine as a subprocess). Needs ``NEXUS_RIE_ENGINE_ROOT`` and optionally
``NEXUS_RIE_PYTHON_BIN``.

Advisory only: no model call, no Planner capability, no runtime wiring, no
required check or merge gate. Writes only ``--output`` and ``--step-summary``.

Exit codes: 0 on any produced artifact (including explicit NOT_APPLICABLE when
the engine is not configured, or ADVISORY_INCOMPLETE on adapter failures);
1 on malformed identity or malformed manifest/arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.services import rie_knowledge_applicability as ka  # noqa: E402
from nexus.services import rie_knowledge_manifest as km  # noqa: E402

ARTIFACT_SCHEMA = "nexus.rie_knowledge_evidence_artifact.v1"
ADVISORY_CLAIM_CEILING = ka.PLANNER_SELECTED_CODEINTEL_CLAIM_CEILING
AUTHORITY_STATEMENT = {
    "planner_capability": False,
    "required_check": False,
    "merge_gate": False,
    "candidate_acceptance": False,
    "policy_owner": False,
}


class IdentityError(ValueError):
    pass


def validate_identity(
    *, repository: str, pr_number: Any, head_sha: str, base_sha: str, current_main_sha: str
) -> dict[str, Any]:
    repo = str(repository or "").strip()
    if "/" not in repo:
        raise IdentityError("repository must be owner/repo")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        raise IdentityError("pr_number must be a positive integer")
    out: dict[str, Any] = {"repository": repo, "pr_number": pr_number}
    for key, value in (
        ("head_sha", head_sha),
        ("base_sha", base_sha),
        ("current_main_sha", current_main_sha or base_sha),
    ):
        text = str(value or "").strip().lower()
        if not ka.SHA40.fullmatch(text):
            raise IdentityError(f"{key} must be a 40-character lowercase hex SHA")
        out[key] = text
    return out


def _artifact(
    disposition: str,
    identity: Mapping[str, Any],
    projection: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema": ARTIFACT_SCHEMA,
        "disposition": disposition,
        "identity": dict(identity),
        "knowledge_applicability": dict(projection),
        "manifest": dict(manifest) if manifest else None,
        "claim_ceiling": ADVISORY_CLAIM_CEILING,
        "authority": dict(AUTHORITY_STATEMENT),
    }


def generate_artifact(
    *,
    repo_root: Path,
    identity: Mapping[str, Any],
    manifest: Mapping[str, Any],
    changes: list[dict[str, str]] | None = None,
    env: Mapping[str, str] | None = None,
    runner: Any = None,
) -> dict[str, Any]:
    """Produce the advisory artifact; adapter failures become explicit artifacts."""
    kwargs: dict[str, Any] = {} if runner is None else {"runner": runner}
    try:
        if changes is None:
            changes = km.git_changes(repo_root, identity["base_sha"], identity["head_sha"])
        built = km.build_manifest_knowledge_evidence(
            manifest=manifest,
            identity=identity,
            changes=changes,
            reader=km.git_blob_reader(repo_root, identity["head_sha"]),
            env=env,
            **kwargs,
        )
    except ka.RieKnowledgeApplicabilityError as exc:
        if exc.code == "RIE_ENGINE_ROOT_NOT_CONFIGURED":
            return _artifact(
                "NOT_APPLICABLE",
                identity,
                ka.not_applicable_projection(["RIE_ENGINE_NOT_CONFIGURED"]),
                None,
            )
        return _artifact(
            "ADVISORY_INCOMPLETE", identity, ka.not_applicable_projection([exc.code]), None
        )
    except km.RieKnowledgeManifestError as exc:
        return _artifact(
            "ADVISORY_INCOMPLETE", identity, ka.not_applicable_projection([exc.code]), None
        )
    projection = built["evidence"]["knowledge_applicability"]
    disposition = "NOT_APPLICABLE" if projection["status"] == "NOT_APPLICABLE" else "OBSERVED"
    return _artifact(disposition, identity, projection, built["manifest"])


def render_step_summary(artifact: Mapping[str, Any]) -> str:
    proj = artifact["knowledge_applicability"]
    ident = artifact["identity"]
    lines = [
        "## RIE Knowledge Applicability (advisory)",
        "",
        f"- Disposition: `{artifact['disposition']}`",
        f"- Status: `{proj['status']}`",
        f"- Identity: `{ident['repository']}` PR `{ident['pr_number']}` head `{ident['head_sha']}` "
        f"base `{ident['base_sha']}`",
        f"- Relation counts: `{json.dumps(proj['relation_counts'], sort_keys=True)}`",
        f"- Report SHA-256: `{proj['report_hash'] or 'none'}`",
        "",
        "### Review-needed artifacts",
    ]
    lines += [f"- `{r}`" for r in proj["affected_artifact_refs"]] or ["- none"]
    lines += ["", "### Evidence gaps"]
    lines += [f"- `{g}`" for g in proj["evidence_gaps"]] or ["- none"]
    lines += [
        "",
        f"Claim ceiling: `{artifact['claim_ceiling']}`",
        "",
        "Advisory evidence only. An affected artifact means review-needed, not semantically wrong. "
        "NOT_APPLICABLE is not CURRENT.",
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.add_argument("--pr-number", type=int)
    p.add_argument("--head-sha", default="")
    p.add_argument("--base-sha", default="")
    p.add_argument("--current-main-sha", default="")
    p.add_argument("--manifest", default="")
    p.add_argument("--output", default="rie-knowledge-evidence.json")
    p.add_argument("--step-summary", default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        identity = validate_identity(
            repository=args.repository,
            pr_number=args.pr_number,
            head_sha=args.head_sha,
            base_sha=args.base_sha,
            current_main_sha=args.current_main_sha,
        )
        repo_root = Path(args.repo_root)
        manifest = km.load_manifest(args.manifest or repo_root / km.DEFAULT_MANIFEST_PATH)
    except (IdentityError, km.RieKnowledgeManifestError) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "reason": str(exc), "claim_ceiling": ADVISORY_CLAIM_CEILING},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    artifact = generate_artifact(repo_root=repo_root, identity=identity, manifest=manifest)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.step_summary:
        Path(args.step_summary).write_text(render_step_summary(artifact), encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
