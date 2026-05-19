from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PROMPT_CONTRACT_VERSION = "nexus_prompt_contract_v2"
PROVIDER_TRANSPORT_CONTRACT_VERSION = "nexus_provider_transport_contract_v1"
VERIFIER_CONTRACT_VERSION = "nexus_verifier_contract_v1"
BENCHMARK_BASIS_CONTRACT_VERSION = "nexus_benchmark_basis_contract_v1"


def sha256_file_if_present(path_value: str | Path) -> str:
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_stable_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable_jsonable(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_prompt_contract_hash(config: Mapping[str, Any]) -> str:
    return sha256_json_payload(
        {
            "schema": PROMPT_CONTRACT_VERSION,
            "session_worker": bool(config.get("session_worker", False)),
            "session_worker_policy": str(config.get("session_worker_policy") or ""),
            "reset_boundary_required": bool(config.get("session_worker", False)),
            "hidden_verifier_mode": bool(config.get("hidden_verifier_mode", False)),
            "prompt_leak_audit": "hidden_only_literals_blocked",
        }
    )


def build_provider_transport_contract_hash(config: Mapping[str, Any]) -> str:
    return sha256_json_payload(
        {
            "schema": PROVIDER_TRANSPORT_CONTRACT_VERSION,
            "without_mode": str(config.get("without_mode") or ""),
            "with_llm_mode": str(config.get("with_llm_mode") or ""),
            "with_model_provider": str(config.get("with_model_provider") or ""),
            "session_worker": bool(config.get("session_worker", False)),
            "session_worker_policy": str(config.get("session_worker_policy") or ""),
            "external_model_export_policy": str(config.get("external_model_export_policy") or ""),
            "outbound_prompt_ledger_required": bool(config.get("outbound_prompt_ledger")),
        }
    )


def build_verifier_contract_hash(config: Mapping[str, Any]) -> str:
    return sha256_json_payload(
        {
            "schema": VERIFIER_CONTRACT_VERSION,
            "hidden_verifier_mode": bool(config.get("hidden_verifier_mode", False)),
            "warning_ledger_required": bool(config.get("warning_ledger_required", False)),
            "wall_ledger_required": bool(config.get("wall_ledger_required", False)),
            "provider_token_measured_required": bool(config.get("provider_token_measured_required", False)),
            "contamination_detector_required": bool(config.get("session_worker", False)),
            "trust_mismatch_policy": "any_mismatch_blocks_public_claim",
        }
    )


def build_benchmark_basis_contract(tasks_file: str | Path) -> dict[str, Any]:
    path = Path(tasks_file) if tasks_file else Path()
    payload: dict[str, Any] = {}
    failures: list[str] = []
    if not tasks_file:
        failures.append("tasks_file_missing")
    elif not path.exists() or not path.is_file():
        failures.append("tasks_file_not_readable")
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"tasks_file_parse_failed:{exc.__class__.__name__}")
    tasks = payload.get("tasks", []) if isinstance(payload.get("tasks"), list) else []
    lanes = sorted({str(task.get("commercial_lane")) for task in tasks if isinstance(task, dict) and task.get("commercial_lane")})
    benchmark_id = str(payload.get("benchmark_id") or "")
    commercial_model_basis_ready = bool(
        not failures
        and payload.get("frozen") is True
        and "commercial" in benchmark_id
        and bool(payload.get("commercial_lane_source"))
        and bool(tasks)
        and all(isinstance(task, dict) and task.get("commercial_lane") for task in tasks)
    )
    if not commercial_model_basis_ready and not failures:
        failures.append("not_commercial_model_basis")
    return {
        "schema": BENCHMARK_BASIS_CONTRACT_VERSION,
        "benchmark_id": benchmark_id,
        "frozen": bool(payload.get("frozen", False)),
        "task_count": len(tasks),
        "commercial_lane_source": str(payload.get("commercial_lane_source") or ""),
        "commercial_lanes": lanes,
        "commercial_model_basis_ready": commercial_model_basis_ready,
        "status": "PASS" if commercial_model_basis_ready else "OBSERVATION_ONLY",
        "failures": failures,
    }


def build_taskset_contract(*, config: Mapping[str, Any], runner_path: str | Path) -> dict[str, Any]:
    disclosure = config.get("public_disclosure_manifest")
    disclosure = disclosure if isinstance(disclosure, dict) else {}
    prompt_contract_hash = str(config.get("prompt_contract_hash") or build_prompt_contract_hash(config))
    provider_transport_contract_hash = str(
        config.get("provider_transport_contract_hash") or build_provider_transport_contract_hash(config)
    )
    verifier_contract_hash = str(config.get("verifier_contract_hash") or build_verifier_contract_hash(config))
    runner_hash = sha256_file_if_present(runner_path)
    taskset_hash = str(config.get("tasks_manifest_hash") or "")
    benchmark_basis_contract = build_benchmark_basis_contract(str(config.get("tasks_file") or ""))
    return {
        "schema": "nexus_taskset_contract_v1",
        "taskset": {
            "path": str(config.get("tasks_file") or ""),
            "sha256": taskset_hash,
            "hash_present": bool(taskset_hash),
        },
        "prompt_contract": {
            "sha256": prompt_contract_hash,
            "hash_present": bool(prompt_contract_hash),
            "status": "HASHED" if prompt_contract_hash else "PENDING_PROMPT_MATERIALIZATION",
        },
        "provider_transport_contract": {
            "sha256": provider_transport_contract_hash,
            "hash_present": bool(provider_transport_contract_hash),
            "without_mode": str(config.get("without_mode") or ""),
            "with_llm_mode": str(config.get("with_llm_mode") or ""),
            "with_model_provider": str(config.get("with_model_provider") or ""),
            "status": "HASHED" if provider_transport_contract_hash else "POLICY_HASH_PENDING",
        },
        "verifier_contract": {
            "sha256": verifier_contract_hash,
            "hash_present": bool(verifier_contract_hash),
            "hidden_verifier_mode": bool(config.get("hidden_verifier_mode")),
            "status": "HASHED" if verifier_contract_hash else "POLICY_HASH_PENDING",
        },
        "runner_contract": {
            "path": str(runner_path),
            "sha256": runner_hash,
            "hash_present": bool(runner_hash),
        },
        "disclosure_manifest": {
            "path": str(disclosure.get("path") or ""),
            "sha256": str(disclosure.get("sha256") or ""),
            "status": str(disclosure.get("status") or "not_provided"),
        },
        "benchmark_basis_contract": benchmark_basis_contract,
        "fixed_public_taskset_ready": bool(
            taskset_hash
            and prompt_contract_hash
            and provider_transport_contract_hash
            and verifier_contract_hash
            and runner_hash
            and disclosure.get("sha256")
        ),
        "claim_boundary": [
            "Public comparison claims require stable taskset, runner, verifier, and disclosure hashes.",
            "Prompt policy hash is provider-neutral; provider transport is recorded separately for disclosure.",
        ],
    }
