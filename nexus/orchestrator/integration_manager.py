"""Fail-closed compatibility quarantine for the retired legacy integration path."""

import warnings as _archived_warnings
from pathlib import Path

from nexus.orchestrator.evidence_collector import EvidenceCollector
from nexus.orchestrator.state_store import StateStore

_archived_warnings.warn(
    "ARCHIVED 2026-10-13 (#1906): retired pre-#957 integration quarantine; use ControlledIntegrationManager; see ARCHIVED_2026-10-13.md. "
    "Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)

LEGACY_INTEGRATION_PATH_RETIRED = (
    "LEGACY_INTEGRATION_PATH_RETIRED_USE_CONTROLLED_INTEGRATION"
)


class IntegrationManager:
    """Compatibility shell for the pre-#957 batch cherry-pick integrator.

    The old implementation mutated a target branch directly and could bypass the
    canonical Candidate acceptance / IntegrationAuthorization / Core-provenance
    chain. It remains importable only so stale callers fail closed with a stable
    machine-readable reason. Supported integration is owned by
    ControlledIntegrationManager through the self-hosted integration lifecycle.
    """

    def __init__(
        self,
        state_store: StateStore,
        evidence_collector: EvidenceCollector,
        *,
        repo_root: str | Path = ".",
        require_clean_preflight: bool = False,
    ):
        self.state_store = state_store
        self.evidence_collector = evidence_collector
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.require_clean_preflight = require_clean_preflight

    def batch_integrate(
        self,
        task_ids: list[str],
        target_branch: str = "main",
    ) -> tuple[list[str], list[str]]:
        """Refuse the retired integration route without any repository effect."""

        del task_ids, target_branch
        return [], [LEGACY_INTEGRATION_PATH_RETIRED]
