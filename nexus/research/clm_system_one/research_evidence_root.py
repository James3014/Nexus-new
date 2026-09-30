from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RELATIVE_ROOT = Path(".nexus") / "research" / "clm_system_one" / "candidate_evidence"
CANONICAL_STATE_RELATIVE_ROOT = Path("research") / "clm_system_one" / "candidate_evidence"


def resolve_research_evidence_root(repo_root: str | Path) -> Path:
    """Resolve the shared System-One research evidence root.

    Evidence must aggregate across short-lived Nexus worktrees so corpus
    readiness observes one durable research corpus.  Explicit configuration
    remains authoritative.  A canonical self-hosted state root is preferred
    when available; repo-local storage remains the compatibility fallback for
    standalone/test environments.
    """

    override = os.getenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    configured_state = os.getenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "").strip()
    if configured_state:
        return (
            Path(configured_state).expanduser().resolve() / CANONICAL_STATE_RELATIVE_ROOT
        ).resolve()

    return (Path(repo_root).expanduser().resolve() / DEFAULT_RELATIVE_ROOT).resolve()
