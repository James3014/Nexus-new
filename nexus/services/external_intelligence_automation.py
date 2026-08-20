from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from nexus.services.external_intelligence import (
    ExternalIntelligenceSidecar,
    ExternalIntelligenceStore,
)
from nexus.services.external_intelligence_closure import (
    CLAIM_CEILING as CLOSURE_CLAIM_CEILING,
)
from nexus.services.external_intelligence_closure import (
    ExternalIntelligenceClosureRuntime,
    TaskCardAuthority,
    VerifierSpec,
    _path_matches,
    parse_task_card_authority,
)
from nexus.services.external_intelligence_fanout import AdaptiveDeepSeekFanoutRuntime, CapacityLease

ISSUE_SCHEMA = "nexus.external_intelligence_issue.v1"
STATE_SCHEMA = "nexus.external_intelligence_automation_state.v1"
FENCE_RE = re.compile(r"```nexus-external-intelligence\s*\n(.*?)\n```", re.DOTALL)
C_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
AMBIGUOUS_STATES = {
    "INTELLIGENCE_DISPATCHING",
    "FANOUT_DISPATCHING",
    "CLOSURE_DISPATCHING",
}
TERMINAL_DISPOSITIONS = {
    "REPAIR_BUDGET_EXHAUSTED",
    "UNIT_REPAIR_REQUIRED",
    "COMPOSITION_REPAIR_REQUIRED",
    "SCOPE_DELTA_REQUIRED",
}
ALLOWED_KEYS = {
    "schema",
    "task_id",
    "revision",
    "main_sha",
    "task_card_ref",
    "task_card_hash",
    "execution_units",
    "unit_verifiers",
    "whole_verifiers",
    "requested_concurrency",
    "blocked_reasons",
    "ready",
    "contract_ready",
    "active_elsewhere",
    "needs_reconciliation",
    "pipeline_mode",
}


class AutomationError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical(value).encode("utf-8"))


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(dict(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _normalize_github_repo(url_or_repo: str) -> str:
    text = str(url_or_repo or "").strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    m = re.search(r"[:/]([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)$", text)
    if m:
        return m.group(1).lower()
    return text.lower()


def _validate_c_slug(value: Any, field: str) -> None:
    if not isinstance(value, str) or not C_SLUG_RE.fullmatch(value):
        raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")


def _validate_relative_path(value: Any) -> str:
    if not isinstance(value, str):
        raise AutomationError("ISSUE_CONTRACT_MUTATION_PATHS_INVALID")
    text = value.strip()
    try:
        path = PurePosixPath(text)
    except (TypeError, ValueError) as exc:
        raise AutomationError("ISSUE_CONTRACT_MUTATION_PATHS_INVALID") from exc
    if not text or path.is_absolute() or ".." in path.parts or "\\" in text or "\x00" in text:
        raise AutomationError("ISSUE_CONTRACT_MUTATION_PATHS_INVALID")
    return path.as_posix()


def _validate_verifier_specs(specs: Any, field: str) -> None:
    if not isinstance(specs, list) or not specs:
        raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
    allowed = {"id", "argv", "owner_unit", "timeout"}
    for spec in specs:
        if not isinstance(spec, Mapping):
            raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
        if set(spec) - allowed:
            raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
        spec_id = spec.get("id")
        if not isinstance(spec_id, str) or not spec_id.strip():
            raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
        argv = spec.get("argv")
        if not isinstance(argv, list) or not argv or len(argv) > 64:
            raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
        for part in argv:
            if not isinstance(part, str) or not part or len(part) > 4096 or "\x00" in part:
                raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
        if "owner_unit" in spec and not isinstance(spec["owner_unit"], str):
            raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
        if "timeout" in spec:
            timeout = spec["timeout"]
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
                raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
            if not 0 < timeout <= 1800:
                raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID")
        try:
            VerifierSpec.from_value(spec)
        except Exception as exc:
            raise AutomationError(f"ISSUE_CONTRACT_{field}_INVALID") from exc


def parse_issue_contract(body: str) -> dict[str, Any]:
    matches = FENCE_RE.findall(body or "")
    if len(matches) != 1:
        raise AutomationError("ISSUE_CONTRACT_BLOCK_REQUIRED")
    try:
        value = json.loads(matches[0])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AutomationError("ISSUE_CONTRACT_JSON_INVALID") from exc
    if not isinstance(value, dict) or set(value) - ALLOWED_KEYS:
        raise AutomationError("ISSUE_CONTRACT_KEYS_INVALID")
    required = {
        "schema",
        "task_id",
        "revision",
        "main_sha",
        "task_card_ref",
        "task_card_hash",
        "execution_units",
        "unit_verifiers",
        "whole_verifiers",
    }
    if set(value) & required != required or value.get("schema") != ISSUE_SCHEMA:
        raise AutomationError("ISSUE_CONTRACT_REQUIRED_FIELDS_MISSING")
    if value.get("pipeline_mode") != "FULL_PIPELINE":
        raise AutomationError("ISSUE_CONTRACT_FULL_PIPELINE_OPT_IN_REQUIRED")
    for key in ("task_id", "revision", "main_sha", "task_card_ref", "task_card_hash"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise AutomationError(f"ISSUE_CONTRACT_{key.upper()}_INVALID")
    _validate_c_slug(value["task_id"], "TASK_ID")
    if not SHA1_RE.fullmatch(value["main_sha"]):
        raise AutomationError("ISSUE_CONTRACT_MAIN_SHA_INVALID")
    if not SHA256_RE.fullmatch(value["task_card_hash"]):
        raise AutomationError("ISSUE_CONTRACT_TASK_CARD_HASH_INVALID")
    units = value.get("execution_units")
    if not isinstance(units, list) or not units:
        raise AutomationError("ISSUE_CONTRACT_EXECUTION_UNITS_INVALID")
    seen: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict):
            raise AutomationError("ISSUE_CONTRACT_UNIT_INVALID")
        allowed_unit = {
            "unit_id",
            "mutation_paths",
            "dependencies_ready",
            "priority",
            "allow_deletions",
        }
        if set(unit) - allowed_unit:
            raise AutomationError("ISSUE_CONTRACT_UNIT_KEYS_INVALID")
        unit_id = unit.get("unit_id")
        paths = unit.get("mutation_paths")
        _validate_c_slug(unit_id, "UNIT_ID")
        if unit_id in seen:
            raise AutomationError("ISSUE_CONTRACT_UNIT_ID_INVALID")
        seen.add(unit_id)
        if not isinstance(paths, list) or not paths:
            raise AutomationError("ISSUE_CONTRACT_MUTATION_PATHS_INVALID")
        normalized_paths: set[str] = set()
        for path in paths:
            normalized = _validate_relative_path(path)
            if normalized in normalized_paths:
                raise AutomationError("ISSUE_CONTRACT_MUTATION_PATHS_INVALID")
            normalized_paths.add(normalized)
        for key in ("dependencies_ready", "allow_deletions"):
            if key in unit and not isinstance(unit[key], bool):
                raise AutomationError(f"ISSUE_CONTRACT_UNIT_{key.upper()}_INVALID")
        if "priority" in unit and (
            not isinstance(unit["priority"], int) or isinstance(unit["priority"], bool)
        ):
            raise AutomationError("ISSUE_CONTRACT_UNIT_PRIORITY_INVALID")
    unit_verifiers = value.get("unit_verifiers")
    if not isinstance(unit_verifiers, dict) or set(unit_verifiers) != seen:
        raise AutomationError("ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID")
    for unit_id in seen:
        _validate_verifier_specs(unit_verifiers[unit_id], "UNIT_VERIFIERS")
    _validate_verifier_specs(value.get("whole_verifiers"), "WHOLE_VERIFIERS")
    if "requested_concurrency" in value:
        rc = value["requested_concurrency"]
        if isinstance(rc, bool) or not isinstance(rc, int) or rc < 1:
            raise AutomationError("ISSUE_CONTRACT_CONCURRENCY_INVALID")
    for key in ("ready", "contract_ready", "active_elsewhere", "needs_reconciliation"):
        if key in value and not isinstance(value[key], bool):
            raise AutomationError(f"ISSUE_CONTRACT_{key.upper()}_INVALID")
    if "blocked_reasons" in value and (
        not isinstance(value["blocked_reasons"], list)
        or any(not isinstance(x, str) for x in value["blocked_reasons"])
    ):
        raise AutomationError("ISSUE_CONTRACT_BLOCKED_REASONS_INVALID")
    return value


@dataclass(frozen=True)
class IssueWorkItem:
    repository: str
    issue_number: int
    title: str
    body: str
    contract: Mapping[str, Any]

    @property
    def identity_hash(self) -> str:
        return _sha256_json({
            "repository": self.repository,
            "issue_number": self.issue_number,
            "revision": self.contract["revision"],
            "main_sha": self.contract["main_sha"],
            "task_card_hash": self.contract["task_card_hash"],
            "contract_hash": _sha256_json(self.contract),
        })


class AutomationStateStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()

    def path_for(self, item: IssueWorkItem) -> Path:
        repo = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.repository)
        return self.root / repo / f"issue-{item.issue_number}-{item.identity_hash}.json"

    def load(self, item: IssueWorkItem) -> dict[str, Any] | None:
        path = self.path_for(item)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema") != STATE_SCHEMA or value.get("identity_hash") != item.identity_hash:
            raise AutomationError("AUTOMATION_STATE_IDENTITY_MISMATCH")
        return value

    def save(self, item: IssueWorkItem, state: str, **extra: Any) -> dict[str, Any]:
        value = {
            "schema": STATE_SCHEMA,
            "repository": item.repository,
            "issue_number": item.issue_number,
            "identity_hash": item.identity_hash,
            "state": state,
            **extra,
        }
        _atomic_json(self.path_for(item), value)
        return value


def compact_publication_payload(closure: Mapping[str, Any]) -> dict[str, Any]:
    capsule = closure.get("control_capsule")
    if not isinstance(capsule, Mapping):
        raise AutomationError("CLOSURE_CAPSULE_REQUIRED")
    return {
        "task_id": capsule.get("task_id"),
        "candidate_commit": capsule.get("candidate_commit"),
        "candidate_tree": capsule.get("candidate_tree"),
        "verification_state": capsule.get("verification_state") or closure.get("status"),
        "current_gate": capsule.get("current_gate"),
        "acceptance_packet_ref": capsule.get("acceptance_packet_ref"),
        "acceptance_packet_sha256": capsule.get("acceptance_packet_sha256"),
        "next_action": capsule.get("next_action"),
        "stop_condition": capsule.get("stop_condition") or capsule.get("stop_if"),
        "claim_ceiling": capsule.get("claim_ceiling") or closure.get("claim_ceiling"),
    }


class ExternalIntelligenceAutomation:
    def __init__(
        self,
        *,
        repository_root: str | os.PathLike[str],
        state_store: AutomationStateStore,
        intelligence_store: ExternalIntelligenceStore,
        sidecar: ExternalIntelligenceSidecar,
        c_runtime: AdaptiveDeepSeekFanoutRuntime | Any,
        d_runtime: ExternalIntelligenceClosureRuntime | Any,
        capacity_factory: Callable[[Mapping[str, Any]], CapacityLease] | None = None,
    ):
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.state_store = state_store
        self.intelligence_store = intelligence_store
        self.sidecar = sidecar
        self.c_runtime = c_runtime
        self.d_runtime = d_runtime
        self.capacity_factory = capacity_factory or self._default_capacity

    @staticmethod
    def _default_capacity(contract: Mapping[str, Any]) -> CapacityLease:
        requested = int(contract.get("requested_concurrency") or 1)
        return CapacityLease(
            requested_concurrency=requested,
            provider_available=requested,
            workspace_available=requested,
            controller_attention_limit=requested,
        )

    def _run_git(self, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

    def _validate_source_lineage(self, repository: str, main_sha: str) -> None:
        remotes_res = self._run_git("remote", "-v")
        if remotes_res.returncode != 0:
            raise AutomationError("REPOSITORY_GIT_ERROR")
        remote_map: dict[str, str] = {}
        for line in remotes_res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                remote_map[parts[0]] = parts[1]
        target_repo = _normalize_github_repo(repository)
        matching_remote: str | None = None
        for r_name, r_url in remote_map.items():
            if _normalize_github_repo(r_url) == target_repo:
                matching_remote = r_name
                break
        if not matching_remote:
            raise AutomationError("REPOSITORY_IDENTITY_MISMATCH")

        tracking_ref = f"refs/remotes/{matching_remote}/main"
        ref_check = self._run_git("rev-parse", "--verify", "--quiet", tracking_ref)
        if ref_check.returncode != 0:
            raise AutomationError("REMOTE_TRACKING_MAIN_NOT_FOUND")

        obj_check = self._run_git("cat-file", "-t", main_sha)
        if obj_check.returncode != 0:
            raise AutomationError("MAIN_SHA_OBJECT_MISSING")
        if obj_check.stdout.strip() != "commit":
            raise AutomationError("MAIN_SHA_NOT_COMMIT")

        anc_check = self._run_git("merge-base", "--is-ancestor", main_sha, tracking_ref)
        if anc_check.returncode != 0:
            raise AutomationError("MAIN_SHA_LINEAGE_MISMATCH")

    def _task_card(self, contract: Mapping[str, Any]) -> tuple[Path, str]:
        rel_str = str(contract.get("task_card_ref") or "")
        try:
            rel = PurePosixPath(rel_str.strip())
        except (TypeError, ValueError) as exc:
            raise AutomationError("TASK_CARD_PATH_INVALID") from exc
        if (
            not rel_str
            or rel.is_absolute()
            or ".." in rel.parts
            or "\\" in rel_str
            or "\x00" in rel_str
        ):
            raise AutomationError("TASK_CARD_PATH_INVALID")
        main_sha = str(contract.get("main_sha") or "")
        spec = f"{main_sha}:{rel.as_posix()}"
        res = subprocess.run(
            ["git", "cat-file", "blob", spec],
            cwd=self.repository_root,
            capture_output=True,
            check=False,
            timeout=30.0,
        )
        if res.returncode != 0:
            raise AutomationError("TASK_CARD_NOT_FOUND")
        raw = res.stdout
        actual = _sha256_bytes(raw)
        if actual != str(contract["task_card_hash"]).lower():
            raise AutomationError("TASK_CARD_HASH_MISMATCH")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AutomationError("TASK_CARD_DECODE_FAILED") from exc
        return Path(rel.as_posix()), text

    def _validate_task_card_authority(
        self, contract: Mapping[str, Any], task_card_text: str
    ) -> TaskCardAuthority:
        authority = parse_task_card_authority(task_card_text)
        if not authority.task_id or authority.task_id != str(contract.get("task_id")):
            raise AutomationError("TASK_CARD_TASK_ID_MISMATCH")
        if not authority.is_executable:
            raise AutomationError("TASK_CARD_STATUS_NOT_EXECUTABLE")
        if not authority.allowed_files:
            raise AutomationError("TASK_CARD_SCOPE_MISMATCH")
        for unit in contract.get("execution_units", []):
            for path in unit.get("mutation_paths", []):
                if not any(_path_matches(path, allowed) for allowed in authority.allowed_files):
                    raise AutomationError("TASK_CARD_SCOPE_MISMATCH")
        for unit in contract.get("execution_units", []):
            if unit.get("allow_deletions") and not authority.allow_deletions:
                raise AutomationError("TASK_CARD_DELETION_FORBIDDEN")
        unit_verifiers = contract.get("unit_verifiers") or {}
        for unit_id, specs in unit_verifiers.items():
            for spec in specs:
                parsed_spec = VerifierSpec.from_value(spec)
                if parsed_spec.argv not in authority.verification_commands:
                    raise AutomationError("VERIFIER_NOT_AUTHORIZED")
        whole_verifiers = contract.get("whole_verifiers") or []
        for spec in whole_verifiers:
            parsed_spec = VerifierSpec.from_value(spec)
            if parsed_spec.argv not in authority.verification_commands:
                raise AutomationError("VERIFIER_NOT_AUTHORIZED")
        return authority

    def _record(self, item: IssueWorkItem) -> dict[str, Any]:
        c = item.contract
        return {
            "repository": item.repository,
            "item_type": "issue",
            "item_id": str(item.issue_number),
            "revision": c["revision"],
            "main_sha": c["main_sha"],
            "task_card_ref": c["task_card_ref"],
            "task_card_hash": c["task_card_hash"],
            "dependency_state": {},
            "overlap_state": {},
            "active_elsewhere": bool(c.get("active_elsewhere", False)),
            "needs_reconciliation": bool(c.get("needs_reconciliation", False)),
            "contract_ready": bool(c.get("contract_ready", False)),
            "ready": bool(c.get("ready", False)),
            "blocked_reasons": list(c.get("blocked_reasons") or []),
        }

    def _sources(self, item: IssueWorkItem, task_card_text: str) -> list[dict[str, Any]]:
        return [
            {
                "kind": "github_issue",
                "ref": f"github://{item.repository}/issues/{item.issue_number}",
                "revision": item.contract["revision"],
                "provenance": "github",
                "content": f"{item.title}\n\n{item.body}",
            },
            {
                "kind": "task_card",
                "ref": item.contract["task_card_ref"],
                "revision": item.contract["task_card_hash"],
                "provenance": "git",
                "content": task_card_text,
            },
        ]

    def _c_units(
        self, item: IssueWorkItem, intelligence: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        request = intelligence.get("request")
        if not isinstance(request, Mapping):
            raise AutomationError("INTELLIGENCE_REQUEST_MISSING")
        request_sha = str(request.get("request_sha256") or "")
        envelope_sha = str(intelligence.get("envelope_sha256") or "")
        envelope_path = self.intelligence_store.root / "envelopes" / f"{request_sha}.json"
        if not envelope_path.is_file():
            raise AutomationError("INTELLIGENCE_ENVELOPE_ARTIFACT_MISSING")
        if _sha256_json(json.loads(envelope_path.read_text(encoding="utf-8"))) != envelope_sha:
            raise AutomationError("INTELLIGENCE_ENVELOPE_ARTIFACT_MISMATCH")
        units: list[dict[str, Any]] = []
        for unit in item.contract["execution_units"]:
            units.append({
                "task_id": item.contract["task_id"],
                "unit_id": unit["unit_id"],
                "envelope_ref": str(envelope_path),
                "envelope_sha256": envelope_sha,
                "expected_base_sha": item.contract["main_sha"],
                "mutation_paths": list(unit["mutation_paths"]),
                "dependencies_ready": unit.get("dependencies_ready", True),
                "priority": unit.get("priority", 0),
                "allow_deletions": unit.get("allow_deletions", False),
            })
        return units

    @staticmethod
    def _valid_receipts(run: Mapping[str, Any], expected_ids: set[str]) -> list[Mapping[str, Any]]:
        errors = run.get("errors") or {}
        receipts = run.get("receipts") or {}
        if errors or not isinstance(receipts, Mapping) or set(receipts) != expected_ids:
            raise AutomationError("FANOUT_INCOMPLETE")
        ordered: list[Mapping[str, Any]] = []
        for unit_id in sorted(expected_ids):
            receipt = receipts[unit_id]
            if (
                not isinstance(receipt, Mapping)
                or receipt.get("status") != "CANDIDATE_READY_FOR_VERIFICATION"
            ):
                raise AutomationError("FANOUT_RECEIPT_NOT_READY")
            ordered.append(receipt)
        return ordered

    def run_issue(
        self, repository: str, issue_number: int, title: str, body: str
    ) -> dict[str, Any]:
        try:
            contract = parse_issue_contract(body)
        except AutomationError as exc:
            return {"state": "BLOCKED", "error": str(exc), "semantic_dispatched": False}
        item = IssueWorkItem(repository, int(issue_number), title, body, contract)
        previous = self.state_store.load(item)
        previous_state = str((previous or {}).get("state") or "")
        resume_from = previous_state
        if previous_state == "COMPLETE" or previous_state in TERMINAL_DISPOSITIONS:
            return {**previous, "reuse": True, "semantic_dispatched": True}
        if previous_state == "RECONCILIATION_REQUIRED":
            if (previous or {}).get("reconcile_only"):
                return {**previous, "reuse": True, "semantic_dispatched": True}
            prior_state = str((previous or {}).get("prior_state") or "")
            if prior_state not in {"INTELLIGENCE_DISPATCHING", "FANOUT_DISPATCHING"}:
                return {**previous, "semantic_dispatched": True}
            resume_from = prior_state
        if resume_from == "CLOSURE_DISPATCHING":
            return self.state_store.save(
                item,
                "RECONCILIATION_REQUIRED",
                prior_state="CLOSURE_DISPATCHING",
                reconcile_only=True,
                semantic_dispatched=True,
            )
        recoverable_states = {
            "INTELLIGENCE_DISPATCHING",
            "INTELLIGENCE_COMPLETED",
            "FANOUT_DISPATCHING",
            "FANOUT_COMPLETED",
        }
        if resume_from and resume_from not in recoverable_states:
            self.state_store.save(item, "DISCOVERED")
        elif not resume_from:
            self.state_store.save(item, "DISCOVERED")
        dispatched = False
        try:
            self._validate_source_lineage(item.repository, str(contract["main_sha"]))
            _, task_card_text = self._task_card(contract)
            self._validate_task_card_authority(contract, task_card_text)
            record = self._record(item)
            self.state_store.save(item, "INTELLIGENCE_DISPATCHING")
            intelligence = self.sidecar.analyze(record, self._sources(item, task_card_text))
            if intelligence.get("status") != "COMPLETED":
                return self.state_store.save(
                    item,
                    "BLOCKED",
                    stage="INTELLIGENCE",
                    result=dict(intelligence),
                    semantic_dispatched=False,
                )
            dispatched = True
            self.state_store.save(
                item,
                "INTELLIGENCE_COMPLETED",
                intelligence_receipt_id=intelligence.get("receipt_id"),
            )

            units = self._c_units(item, intelligence)
            self.state_store.save(item, "FANOUT_DISPATCHING")
            fanout = self.c_runtime.run(units, self.capacity_factory(contract))
            receipts = self._valid_receipts(fanout, {unit["unit_id"] for unit in units})
            self.state_store.save(item, "FANOUT_COMPLETED", run_sha256=fanout.get("run_sha256"))

            self.state_store.save(item, "CLOSURE_DISPATCHING")
            closure = self.d_runtime.close_task(
                main_sha=str(contract["main_sha"]),
                unit_receipts=receipts,
                unit_verifiers=contract["unit_verifiers"],
                whole_verifiers=contract["whole_verifiers"],
                task_card_ref=contract["task_card_ref"],
                task_card_hash=contract["task_card_hash"],
                external_intelligence_refs=[str(intelligence.get("receipt_id") or "")],
            )
            if (
                closure.get("status") != CLOSURE_CLAIM_CEILING
                or not isinstance(closure.get("control_capsule"), Mapping)
                or not closure["control_capsule"]
            ):
                closure_status = str(closure.get("status") or "")
                if closure_status in TERMINAL_DISPOSITIONS:
                    return self.state_store.save(
                        item,
                        closure_status,
                        closure_status=closure_status,
                        closure_run_id=closure.get("run_id"),
                        semantic_dispatched=True,
                    )
                return self.state_store.save(
                    item,
                    "BLOCKED",
                    stage="CLOSURE",
                    closure_status=closure.get("status"),
                    semantic_dispatched=True,
                )
            publication = compact_publication_payload(closure)
            return self.state_store.save(
                item,
                "COMPLETE",
                intelligence_receipt_id=intelligence.get("receipt_id"),
                fanout_run_sha256=fanout.get("run_sha256"),
                closure_run_id=closure.get("run_id"),
                publication=publication,
                semantic_dispatched=True,
            )
        except AutomationError as exc:
            return self.state_store.save(
                item, "BLOCKED", error=str(exc), semantic_dispatched=dispatched
            )
        except Exception as exc:
            current = self.state_store.load(item) or {}
            if current.get("state") in AMBIGUOUS_STATES:
                return self.state_store.save(
                    item,
                    "RECONCILIATION_REQUIRED",
                    prior_state=current.get("state"),
                    error=type(exc).__name__,
                    reconcile_only=True,
                    semantic_dispatched=dispatched,
                )
            return self.state_store.save(
                item, "BLOCKED", error=type(exc).__name__, semantic_dispatched=dispatched
            )


__all__ = [
    "AMBIGUOUS_STATES",
    "AutomationError",
    "AutomationStateStore",
    "ExternalIntelligenceAutomation",
    "ISSUE_SCHEMA",
    "IssueWorkItem",
    "TERMINAL_DISPOSITIONS",
    "_normalize_github_repo",
    "compact_publication_payload",
    "parse_issue_contract",
]
