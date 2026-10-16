"""Planner-selected codeintel hook for RIE knowledge applicability (#1579 G3 seam).

Runs inside the ``codeintel`` capability invoker, which the runtime only calls
when CapabilityPlanner selected ``codeintel``.  It adds a bounded
``knowledge_applicability`` evidence fragment; it never selects, routes, gates,
approves or merges anything, and it never raises into the codeintel stage.

RIE semantics stay in RIE: the engine is only reached through
``rie_knowledge_applicability``'s subprocess adapter.

Fail-closed rules for this sub-evidence only:
* no caller identity hint / unusable revision / engine not configured / HEAD
  mismatch -> explicit ``NOT_APPLICABLE`` (never ``CURRENT``);
* engine, report or manifest integrity failure -> ``INCOMPLETE`` with gap
  ``RIE_KNOWLEDGE_REJECTED:<code>`` (never ``CURRENT``).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from nexus.services import rie_knowledge_applicability as ka
from nexus.services import rie_knowledge_manifest as km

IDENTITY_HINT_KEY = "rie_knowledge_identity"
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GIT_TIMEOUT_SECONDS = 30


def validate_identity_hint(hint: Any) -> dict[str, Any] | None:
    """Return a normalized hint (without head_sha) or None when unusable."""
    if not isinstance(hint, Mapping):
        return None
    repository = hint.get("repository")
    pr_number = hint.get("pr_number")
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        return None
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        return None
    base = str(hint.get("base_sha") or "").strip().lower()
    main = str(hint.get("current_main_sha") or base).strip().lower()
    if not ka.SHA40.fullmatch(base) or not ka.SHA40.fullmatch(main):
        return None
    return {
        "repository": repository,
        "pr_number": pr_number,
        "base_sha": base,
        "current_main_sha": main,
    }


def _not_applicable(*gaps: str) -> dict[str, Any]:
    return {"knowledge_applicability": ka.not_applicable_projection(list(gaps))}


def _rejected(code: str) -> dict[str, Any]:
    projection = ka.not_applicable_projection([f"RIE_KNOWLEDGE_REJECTED:{code}"])
    projection["status"] = "INCOMPLETE"
    return {"knowledge_applicability": projection}


def _engine_runner() -> Any:
    """Subprocess runner used for the RIE engine (tests substitute a stub here)."""
    return subprocess.run


def _git_head(workspace: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    head = str(proc.stdout or "").strip().lower()
    return head if proc.returncode == 0 and ka.SHA40.fullmatch(head) else None


def knowledge_applicability_evidence(
    context: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = None,
) -> dict[str, Any]:
    """Return ``{"knowledge_applicability": projection}``; never raises."""
    try:
        return _evidence(context, env=env, runner=runner)
    except Exception as exc:  # fail closed for this sub-evidence only
        return _rejected(f"HOOK_{type(exc).__name__}"[:40])


def _evidence(
    context: Mapping[str, Any], *, env: Mapping[str, str] | None, runner: Any
) -> dict[str, Any]:
    ctx = context if isinstance(context, Mapping) else {}
    hint = validate_identity_hint(ctx.get(IDENTITY_HINT_KEY))
    if hint is None:
        return _not_applicable("REVISION_IDENTITY_UNAVAILABLE")
    head = str(ctx.get("target_revision") or "").strip().lower()
    workspace = str(ctx.get("workspace_root") or "").strip()
    if not ka.SHA40.fullmatch(head) or not workspace:
        return _not_applicable("REVISION_IDENTITY_UNAVAILABLE")
    try:
        ka.resolve_engine_config(env)
    except ka.RieKnowledgeApplicabilityError as exc:
        return _not_applicable(exc.code)
    root = Path(workspace)
    if _git_head(root) != head:
        return _not_applicable("HEAD_REVISION_MISMATCH")
    identity = {**hint, "head_sha": head}
    try:
        manifest = km.load_manifest(root / km.DEFAULT_MANIFEST_PATH)
        changes = km.git_changes(root, identity["base_sha"], head)
        built = km.build_manifest_knowledge_evidence(
            manifest=manifest,
            identity=identity,
            changes=changes,
            reader=km.git_blob_reader(root, head),
            env=env,
            runner=runner if runner is not None else _engine_runner(),
        )
    except ka.RieKnowledgeApplicabilityError as exc:
        if exc.code == "RIE_ENGINE_ROOT_NOT_CONFIGURED":
            return _not_applicable(exc.code)
        return _rejected(exc.code)
    except km.RieKnowledgeManifestError as exc:
        return _rejected(exc.code)
    return {"knowledge_applicability": built["evidence"]["knowledge_applicability"]}
