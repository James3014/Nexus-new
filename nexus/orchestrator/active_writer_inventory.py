"""Canonical complete active-writer inventory collector (#98).

Discovers and validates all active writers across canonical physical entrypoints:
1. DIRECT_CANONICAL (Dev MCP direct provenance)
2. DIRECT_DELEGATED (RDC delegated provenance)
3. GOVERNED / ISOLATED_TARGET (Governed isolated Target worktree ownership)
4. Qualified LOCAL writer provenance (if enabled/configured)
5. External workers and Agy operations (other authoritative writer entrypoints)

Invariants:
- Source-bound, freshness-bound, reconstructable; no second durable registry.
- Fail-closed: inventory_complete is True iff all canonical surfaces are probed,
  uncorrupted, and verified.
- Process silence != released: if a process is dead without terminal receipt,
  it is OUTCOME_UNKNOWN -> RECONCILE_REQUIRED.
- Heartbeat stale (>120s) -> STALE.
- Corrupt JSON or unreadable records -> RECONCILE_REQUIRED.
- Unresolved prior effects -> RECONCILE_REQUIRED.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from nexus.orchestrator.worktree_manager import (
    CONFLICT_RECONCILE_REQUIRED,
    CONFLICT_STALE,
    CONFLICT_UNKNOWN,
)
from nexus.services.agy_operation_journal import AgyOperationJournal
from nexus.services.direct_operation_journal import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    DirectOperationJournal,
    DirectOperationJournalError,
    _process_alive,
)
from nexus.services.live_execution_provenance import (
    _DEV_MCP_OPERATION_PREFIX,
    _EXTERNAL_WORKER_PREFIXES,
    _RDC_OPERATION_PREFIX,
    PRODUCER_SCHEMA_DEV_MCP_V1,
    PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
    PRODUCER_SCHEMA_RDC_V1,
    ProvenanceContractError,
    read_operation_journal_evidence,
    _agy_operation_root,
    _dev_mcp_operation_root,
    _external_worker_operation_root,
    _rdc_operation_root,
)

ACTIVE_WRITER_INVENTORY_SCHEMA = "nexus.orchestrator.active_writer_inventory.v1"
ACTIVE_WRITER_INVENTORY_CLAIM_CEILING = "CANONICAL_ACTIVE_WRITER_INVENTORY_ONLY"


@dataclass(frozen=True)
class ActiveWriterInventoryResult:
    """Result of scanning all canonical physical entrypoints for active writers."""

    active_writers: list[dict[str, Any]]
    complete: bool
    disposition: Optional[str] = None
    reason: Optional[str] = None
    conflicting_writers: list[Any] = field(default_factory=list)
    sources_scanned: tuple[str, ...] = ()
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _heartbeat_age_seconds(last_heartbeat: Any, now_ts: Optional[float] = None) -> Optional[float]:
    if not last_heartbeat or not isinstance(last_heartbeat, str):
        return None
    try:
        ts = datetime.fromisoformat(last_heartbeat.replace("Z", "+00:00")).timestamp()
        current = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()
        return max(0.0, current - ts)
    except (ValueError, TypeError):
        return None


def _matches_controller_repo(record: Mapping[str, Any], controller_root: Path) -> bool:
    target_repo = record.get("repo_root") or record.get("cwd")
    if not target_repo:
        # If repo is unspecified, cannot assume it belongs to another repo:
        # fail-closed: treat as matching this repo
        return True
    try:
        target_path = Path(str(target_repo)).expanduser().resolve()
        ctrl_path = controller_root.expanduser().resolve()
        if target_path == ctrl_path:
            return True
        if ctrl_path in target_path.parents:
            return True
        return False
    except Exception:
        return True


class ActiveWriterInventoryCollector:
    """Canonical inventory collector scanning all active physical producer entrypoints."""

    def __init__(
        self,
        *,
        heartbeat_stale_seconds: float = 120.0,
    ) -> None:
        self.heartbeat_stale_seconds = float(heartbeat_stale_seconds)

    def _resolve_dev_mcp_root(self) -> Path:
        return _dev_mcp_operation_root()

    def _resolve_rdc_root(self) -> Path:
        return _rdc_operation_root()

    def _resolve_external_worker_root(self) -> Path:
        return _external_worker_operation_root()

    def _resolve_agy_root(self) -> Path:
        return _agy_operation_root()

    def _resolve_local_writer_root(self) -> Optional[Path]:
        env_val = os.getenv("NEXUS_LOCAL_WRITER_ROOT")
        if env_val:
            return Path(env_val).expanduser().resolve()
        default_dir = Path.home() / ".local/state/nexus-local-writers"
        if default_dir.is_dir():
            return default_dir.resolve()
        return None

    def _scan_operations_directory(
        self,
        journal: DirectOperationJournal,
        default_mutation_mode: str,
        controller_root: Path,
        expected_revision: Optional[str],
        source_name: str,
        *,
        required: bool,
    ) -> tuple[Optional[ActiveWriterInventoryResult], list[dict[str, Any]]]:
        """Read one canonical operation journal through its owning API."""
        root = journal.root.expanduser().resolve()
        operations_dir = journal.operations_dir.expanduser().resolve()

        if not root.exists():
            if required:
                return (
                    ActiveWriterInventoryResult(
                        active_writers=[],
                        complete=False,
                        disposition=CONFLICT_UNKNOWN,
                        reason=f"CANONICAL_PRODUCER_ROOT_UNAVAILABLE: {source_name}: {root}",
                        sources_scanned=(source_name,),
                    ),
                    [],
                )
            return None, []

        if not root.is_dir():
            return (
                ActiveWriterInventoryResult(
                    active_writers=[],
                    complete=False,
                    disposition=CONFLICT_RECONCILE_REQUIRED,
                    reason=f"CORRUPT_PRODUCER_DIRECTORY: {root} is not a directory",
                    sources_scanned=(source_name,),
                ),
                [],
            )

        # A configured producer root may legitimately have no operations yet.
        # The root itself is the availability witness; a missing configured root
        # above is never interpreted as an empty inventory.
        if not operations_dir.exists():
            return None, []
        if not operations_dir.is_dir():
            return (
                ActiveWriterInventoryResult(
                    active_writers=[],
                    complete=False,
                    disposition=CONFLICT_RECONCILE_REQUIRED,
                    reason=f"CORRUPT_PRODUCER_DIRECTORY: {operations_dir} is not a directory",
                    sources_scanned=(source_name,),
                ),
                [],
            )

        active_writers: list[dict[str, Any]] = []
        try:
            entries = sorted(operations_dir.iterdir())
        except OSError as exc:
            return (
                ActiveWriterInventoryResult(
                    active_writers=[],
                    complete=False,
                    disposition=CONFLICT_UNKNOWN,
                    reason=f"PRODUCER_DIRECTORY_INACCESSIBLE: {operations_dir}: {exc}",
                    sources_scanned=(source_name,),
                ),
                [],
            )

        for entry in entries:
            if entry.name.startswith("."):
                continue
            if not entry.is_dir():
                return (
                    ActiveWriterInventoryResult(
                        active_writers=[],
                        complete=False,
                        disposition=CONFLICT_RECONCILE_REQUIRED,
                        reason=f"CORRUPT_PRODUCER_ENTRY: unexpected file in operations dir: {entry.name}",
                        sources_scanned=(source_name,),
                    ),
                    [],
                )

            try:
                # Critical trust boundary: schema-shaped raw JSON is not producer
                # proof.  Reuse #1266's canonical owning-read adapter so root,
                # operation-id, record path, schema, status, and immutable read
                # identity are all bound before #98 consumes the record.
                evidence = read_operation_journal_evidence(journal, entry.name)
                data = evidence.record
            except (DirectOperationJournalError, ProvenanceContractError) as exc:
                return (
                    ActiveWriterInventoryResult(
                        active_writers=[],
                        complete=False,
                        disposition=CONFLICT_RECONCILE_REQUIRED,
                        reason=f"CORRUPT_CANONICAL_OPERATION_RECORD_DETECTED: {source_name}: {entry.name}: {exc}",
                        conflicting_writers=[entry.name],
                        sources_scanned=(source_name,),
                    ),
                    [],
                )

            if not _matches_controller_repo(data, controller_root):
                continue

            status = str(data.get("status") or "").upper()
            reconcil = data.get("reconciliation")
            reconcil_res = reconcil.get("result") if isinstance(reconcil, Mapping) else None

            if status == "OUTCOME_UNKNOWN" or reconcil_res == "OUTCOME_UNKNOWN":
                return (
                    ActiveWriterInventoryResult(
                        active_writers=[],
                        complete=False,
                        disposition=CONFLICT_RECONCILE_REQUIRED,
                        reason=f"ACTIVE_WRITER_UNRESOLVED_PRIOR_EFFECTS: operation {entry.name} has OUTCOME_UNKNOWN",
                        conflicting_writers=[entry.name],
                        sources_scanned=(source_name,),
                    ),
                    [],
                )

            if status in ACTIVE_STATES:
                pid = data.get("pid")
                if status != "QUEUED" and pid is None and not data.get("provider_session_id"):
                    return (
                        ActiveWriterInventoryResult(
                            active_writers=[],
                            complete=False,
                            disposition=CONFLICT_RECONCILE_REQUIRED,
                            reason=f"ACTIVE_WRITER_PHYSICAL_IDENTITY_MISSING: operation {entry.name}",
                            conflicting_writers=[entry.name],
                            sources_scanned=(source_name,),
                        ),
                        [],
                    )
                if pid is not None and not _process_alive(pid):
                    return (
                        ActiveWriterInventoryResult(
                            active_writers=[],
                            complete=False,
                            disposition=CONFLICT_RECONCILE_REQUIRED,
                            reason=f"PROCESS_SILENCE_WITHOUT_TERMINAL_RECEIPT: operation {entry.name} pid {pid} is dead without terminal receipt",
                            conflicting_writers=[entry.name],
                            sources_scanned=(source_name,),
                        ),
                        [],
                    )

                heartbeat = data.get("last_heartbeat_at")
                age = _heartbeat_age_seconds(heartbeat)
                if status != "QUEUED" and age is None:
                    return (
                        ActiveWriterInventoryResult(
                            active_writers=[],
                            complete=False,
                            disposition=CONFLICT_STALE,
                            reason=f"ACTIVE_STALE_HEARTBEAT: operation {entry.name} has no valid heartbeat",
                            conflicting_writers=[entry.name],
                            sources_scanned=(source_name,),
                        ),
                        [],
                    )
                if age is not None and age > self.heartbeat_stale_seconds:
                    return (
                        ActiveWriterInventoryResult(
                            active_writers=[],
                            complete=False,
                            disposition=CONFLICT_STALE,
                            reason=f"ACTIVE_STALE_HEARTBEAT: operation {entry.name} heartbeat age {age:.1f}s exceeds {self.heartbeat_stale_seconds:.1f}s",
                            conflicting_writers=[entry.name],
                            sources_scanned=(source_name,),
                        ),
                        [],
                    )

                writer = self._normalize_operation_writer(
                    data,
                    default_mode=default_mutation_mode,
                    controller_root=controller_root,
                    expected_revision=expected_revision,
                )
                active_writers.append(writer)

            elif status in TERMINAL_STATES:
                if data.get("unknown_effect_refs") or data.get("unresolved_effects"):
                    return (
                        ActiveWriterInventoryResult(
                            active_writers=[],
                            complete=False,
                            disposition=CONFLICT_RECONCILE_REQUIRED,
                            reason=f"ACTIVE_WRITER_UNRESOLVED_PRIOR_EFFECTS: operation {entry.name}",
                            conflicting_writers=[entry.name],
                            sources_scanned=(source_name,),
                        ),
                        [],
                    )

        return None, active_writers

    def _normalize_operation_writer(
        self,
        record: Mapping[str, Any],
        *,
        default_mode: str,
        controller_root: Path,
        expected_revision: Optional[str],
    ) -> dict[str, Any]:
        op_id = str(record.get("operation_id") or "")
        task_id = str(record.get("task_id") or op_id)
        attempt_id = str(record.get("attempt_id") or f"attempt-{op_id}")
        mode = str(record.get("mutation_mode") or default_mode).upper()
        rev = str(
            record.get("controller_revision")
            or record.get("base_head")
            or record.get("runtime_revision")
            or expected_revision
            or ""
        ).strip()
        allowed = (
            record.get("allowed_files")
            or record.get("allowed_paths")
            or (record.get("contract") or {}).get("allowed_files")
            or (record.get("contract") or {}).get("allowed_paths")
            or record.get("observed_changed_paths")
            or []
        )
        if isinstance(allowed, (str, bytes)):
            allowed = [str(allowed)]
        else:
            allowed = list(allowed)

        contract = record.get("contract")
        if not isinstance(contract, Mapping):
            contract = {
                "task_id": task_id,
                "controller_repo_root": str(controller_root),
                "controller_revision": rev,
                "allowed_files": allowed,
                "mutation_mode": mode,
            }

        return {
            "task_id": task_id,
            "attempt_id": attempt_id,
            "lease_id": str(record.get("lease_id") or f"lease-{op_id}"),
            "status": str(record.get("status") or "RUNNING"),
            "controller_worktree": str(controller_root),
            "controller_revision": rev,
            "mutation_mode": mode,
            "contract": contract,
            "allowed_files": allowed,
            "unknown_effect_refs": record.get("unknown_effect_refs"),
            "unresolved_effects": record.get("unresolved_effects"),
        }

    def collect(
        self,
        controller_root: Path | str,
        *,
        expected_revision: Optional[str] = None,
        target_records: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> ActiveWriterInventoryResult:
        """Scan all canonical producer roots and return complete inventory."""
        ctrl_root = Path(controller_root).expanduser().resolve()
        all_active: list[dict[str, Any]] = []
        scanned_sources: list[str] = []

        # 1. Governed / Isolated Target records
        scanned_sources.append("GOVERNED_TARGETS")
        if target_records is not None:
            for r in target_records:
                if not isinstance(r, Mapping) or r.get("invalid"):
                    return ActiveWriterInventoryResult(
                        active_writers=[],
                        complete=False,
                        disposition=CONFLICT_RECONCILE_REQUIRED,
                        reason="CORRUPT_CANONICAL_OWNERSHIP_RECORD_DETECTED",
                        conflicting_writers=[
                            str(r.get("task_id") if isinstance(r, Mapping) else "")
                        ],
                        sources_scanned=tuple(scanned_sources),
                    )
                if r.get("unknown_effect_refs") or r.get("unresolved_effects"):
                    return ActiveWriterInventoryResult(
                        active_writers=[],
                        complete=False,
                        disposition=CONFLICT_RECONCILE_REQUIRED,
                        reason="ACTIVE_WRITER_UNRESOLVED_PRIOR_EFFECTS",
                        conflicting_writers=[str(r.get("task_id") or "")],
                        sources_scanned=tuple(scanned_sources),
                    )
                all_active.append(dict(r))

        # 2. DIRECT_CANONICAL (Dev MCP Direct Provenance)
        scanned_sources.append("DEV_MCP")
        dev_mcp_root = self._resolve_dev_mcp_root()
        dev_journal = DirectOperationJournal(
            dev_mcp_root,
            schema=PRODUCER_SCHEMA_DEV_MCP_V1,
            operation_prefix=_DEV_MCP_OPERATION_PREFIX,
        )
        err, writers = self._scan_operations_directory(
            dev_journal,
            default_mutation_mode="DIRECT_CANONICAL",
            controller_root=ctrl_root,
            expected_revision=expected_revision,
            source_name="DEV_MCP",
            required=bool(os.getenv("NEXUS_DEV_MCP_OPERATION_ROOT")),
        )
        if err is not None:
            return err
        all_active.extend(writers)

        # 3. DIRECT_DELEGATED (RDC Delegated Provenance)
        scanned_sources.append("RDC")
        rdc_root = self._resolve_rdc_root()
        rdc_journal = DirectOperationJournal(
            rdc_root,
            schema=PRODUCER_SCHEMA_RDC_V1,
            operation_prefix=_RDC_OPERATION_PREFIX,
        )
        err, writers = self._scan_operations_directory(
            rdc_journal,
            default_mutation_mode="DIRECT_DELEGATED",
            controller_root=ctrl_root,
            expected_revision=expected_revision,
            source_name="RDC",
            required=bool(os.getenv("NEXUS_RDC_OPERATION_ROOT")),
        )
        if err is not None:
            return err
        all_active.extend(writers)

        # 4. External Workers (Codex, Cline, OpenCode, Grok)
        scanned_sources.append("EXTERNAL_WORKERS")
        ext_root = self._resolve_external_worker_root()
        ext_required = bool(os.getenv("NEXUS_EXTERNAL_WORKER_OPERATION_ROOT"))
        if ext_required and not ext_root.exists():
            return ActiveWriterInventoryResult(
                active_writers=[],
                complete=False,
                disposition=CONFLICT_UNKNOWN,
                reason=f"CANONICAL_PRODUCER_ROOT_UNAVAILABLE: EXTERNAL_WORKERS: {ext_root}",
                sources_scanned=tuple(scanned_sources),
            )
        for provider in sorted(_EXTERNAL_WORKER_PREFIXES.keys()):
            journal = DirectOperationJournal(
                ext_root / provider,
                schema=PRODUCER_SCHEMA_EXTERNAL_WORKER_V1,
                operation_prefix=_EXTERNAL_WORKER_PREFIXES[provider],
            )
            err, writers = self._scan_operations_directory(
                journal,
                default_mutation_mode="DIRECT_DELEGATED",
                controller_root=ctrl_root,
                expected_revision=expected_revision,
                source_name=f"EXTERNAL_{provider.upper()}",
                required=ext_required and (ext_root / provider).exists(),
            )
            if err is not None:
                return err
            all_active.extend(writers)

        # 5. Agy Operations
        scanned_sources.append("AGY")
        agy_root = self._resolve_agy_root()
        agy_journal = AgyOperationJournal(agy_root)
        err, writers = self._scan_operations_directory(
            agy_journal,
            default_mutation_mode="DIRECT_DELEGATED",
            controller_root=ctrl_root,
            expected_revision=expected_revision,
            source_name="AGY",
            required=bool(os.getenv("NEXUS_AGY_OPERATION_ROOT")),
        )
        if err is not None:
            return err
        all_active.extend(writers)

        # 6. Qualified LOCAL writer provenance.
        # #1266 does not currently define a trusted local-writer producer.  If a
        # local writer surface is configured/present, #98 must therefore remain
        # UNKNOWN rather than treating schema-shaped raw files as canonical.
        local_root = self._resolve_local_writer_root()
        if local_root is not None:
            scanned_sources.append("LOCAL_WRITER")
            return ActiveWriterInventoryResult(
                active_writers=[],
                complete=False,
                disposition=CONFLICT_UNKNOWN,
                reason=f"LOCAL_WRITER_CANONICAL_PRODUCER_UNAVAILABLE: {local_root}",
                sources_scanned=tuple(scanned_sources),
            )

        return ActiveWriterInventoryResult(
            active_writers=all_active,
            complete=True,
            disposition=None,
            reason=None,
            conflicting_writers=[],
            sources_scanned=tuple(scanned_sources),
        )


def collect_active_writer_inventory(
    controller_root: Path | str,
    *,
    expected_revision: Optional[str] = None,
    target_records: Optional[Sequence[Mapping[str, Any]]] = None,
    heartbeat_stale_seconds: float = 120.0,
) -> ActiveWriterInventoryResult:
    """Convenience helper to collect the canonical complete active-writer inventory."""
    collector = ActiveWriterInventoryCollector(
        heartbeat_stale_seconds=heartbeat_stale_seconds,
    )
    return collector.collect(
        controller_root,
        expected_revision=expected_revision,
        target_records=target_records,
    )
