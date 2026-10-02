from __future__ import annotations

import argparse
import ast
import base64
import datetime as dt
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from nexus.research.hybrid_replication_pipeline import (
    FrozenStackOutcome,
    RawRouteResult,
    TaskSnapshot,
)
from nexus.services.direct_operation_journal import TERMINAL_STATES

EXACT_AGY_MODEL = "gemini-3.8-flash-medium"
CANONICAL_AGY_DISPATCH_NAME = "nexus-agy-dispatch"
CANONICAL_AGY_DISPATCH_SHA256 = "238979e3e83d3868deba1f53faf73313d0f62379d52894e9ca0ec54bc519d63f"
AGY_PROVIDER_TERMINAL_GRACE_SECONDS = 30.0
MAX_AGY_PROVIDER_OUTPUT_BYTES = 5_000_000
AGY_RAW_RECEIPT_SCHEMA = "nexus.hybrid_replication.agy_live_raw.v1"
AGY_SHADOW_CANDIDATE_SCHEMA = "nexus.hybrid_replication.agy_shadow_candidate.v1"

D0_IMPLEMENTATION_SHA256 = "cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9"
D0_DEFAULT_PATH = Path(
    "/Users/james/workspace/nexus-hardware-lab/local-capability-expansion-v1/"
    "task-localization-v1/d0_v2_develop.py"
)
D0_DEFAULT_FREEZE = D0_DEFAULT_PATH.with_name("D0_V2_FROZEN.json")
D0_FREEZE_SHA256 = "f04fdeea8ddb8cbaa2216aa783a7fe510da7c2f8625f50763a0d59d5e2234eee"
CODEX_EXECUTABLE_SHA256 = "61b0194f3bb6534439c8d26a3ed57d0805f84b884588b761795323eeb92fcf70"
FROZEN_RECEIPT_SHA256S = {
    "r3": "77dee0030b022240ec8b23c388b0a957dc70878dc28ebae03d0d4d720402db37",
    "d2": "4873ae4c96b63a0306c5dcc3afff039ab8df8ff6c7ee7070382eebb4d4268e79",
    "dm1": "d85acab617dca8e2eab04c0e63246b41e1382ca0871607a96a424828bb05be99",
    "re2": "ae1414c73107140b234d38178165769faad9d33f217a3b1f8064953e144efc63",
}
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DM1_TOP_PROBABILITY_MIN = 0.70
DM1_MARGIN_MIN = 0.30
DEFAULT_LIVE_BINDING = Path(
    "/Users/james/nexus-hybrid-deployment-replication-20260930/live/LIVE_BINDING.json"
)

DEFAULT_REPO_ROOTS = {
    "James3014/Nexus-new": "/Users/james/Workspace/Nexus-new",
    "James3014/devspace": "/Users/james/Workspace/devspace",
    "James3014/nexus-core": "/Users/james/Workspace/nexus-core",
    "James3014/nexus-learning": "/Users/james/Workspace/nexus-learning",
    "James3014/nexus-open-swe-runtime": "/Users/james/Workspace/nexus-open-swe-runtime",
    "James3014/repository-intelligence-engine": (
        "/Users/james/Workspace/repository-intelligence-engine"
    ),
    "James3014/nexus-runtime": "/Users/james/Workspace/nexus-runtime",
    "James3014/nexus-opencli-reviewer": "/Users/james/Workspace/nexus-opencli-reviewer",
}

_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:[A-Za-z0-9_.-]+/)+"
    r"(?:[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|mjs|cjs|json|ya?ml|toml|ini|cfg|sh|md|txt)))"
)

_FORBIDDEN_SHADOW_COMMANDS = (
    re.compile(r"\bgit\s+(?:push|fetch|pull|clone|commit)\b", re.IGNORECASE),
    re.compile(r"\b(?:gh|curl|wget|ssh)\s+", re.IGNORECASE),
    re.compile(
        r"\b(?:pip|npm|pnpm|yarn)\s+install\b|\buv\s+(?:pip\s+)?install\b",
        re.IGNORECASE,
    ),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        list(argv),
        cwd=None if cwd is None else str(cwd),
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def extract_literal_paths(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _PATH_RE.finditer(text):
        path = match.group(1).lstrip("./")
        if path not in found:
            found.append(path)
    return tuple(found)


def classify_frozen_task_family(*, title: str, body: str) -> str:
    text = f"{title}\n{body}".lower()
    a_markers = (
        "perform dependency discovery",
        "direct imported modules",
        "repository files that directly import",
        "public top-level functions/classes",
    )
    if all(marker in text for marker in a_markers):
        return "A"

    b_markers = (
        "repository localization",
        "identify and rank",
        "rank the supplied candidate",
        "rank supplied candidate",
        "which candidate file",
        "which file",
        "locate the file",
        "localize the file",
        "localise the file",
    )
    mutation_markers = (
        "implement ",
        "fix ",
        "repair ",
        "change ",
        "add regression",
        "modify ",
        "delete ",
        "refactor ",
    )
    if any(marker in text for marker in b_markers) and not any(
        marker in text for marker in mutation_markers
    ):
        return "B"
    return "C"


def build_d2_candidate_packet(
    *,
    task_key: str,
    source_revision: str,
    task_contract: str,
    literal_paths: Sequence[str],
    ranked_paths: Sequence[str],
    evidence: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    ordered: list[str] = []
    literal_set = set(literal_paths)
    for path in [*literal_paths, *ranked_paths]:
        if path not in ordered:
            ordered.append(path)
        if len(ordered) == 8:
            break

    catalog = []
    for index, path in enumerate(ordered, 1):
        why = list(evidence.get(path, ()))
        if path in literal_set and "literal_path_in_issue_body" not in why:
            why.insert(0, "literal_path_in_issue_body")
        catalog.append({
            "id": f"C{index}",
            "path": path,
            "source": "LITERAL_TASK_PATH" if path in literal_set else "D0_V2_FROZEN",
            "evidence": why[:12],
        })

    payload = {
        "schema": "nexus.hybrid_replication.d2_live_packet.v1",
        "task_key": task_key,
        "source_revision": source_revision,
        "task_contract_sha256": _sha256_bytes(task_contract.encode("utf-8")),
        "candidate_catalog": catalog,
        "shaping_rule": (
            "Preserve literal task paths before frozen D0_V2 top-8; de-duplicate by "
            "first occurrence; preserve candidate evidence/provenance; no evidence deletion "
            "or learned/generative compression."
        ),
    }
    payload["packet_sha256"] = _sha256_bytes(_canonical_bytes(payload))
    return payload


def _parse_timestamp(value: str) -> dt.datetime | None:
    text = value.strip()
    if not text:
        return None
    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def resolve_ground_truth_payload(
    *,
    issue: Mapping[str, Any],
    merged_prs: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if str(issue.get("state") or "") != "closed":
        return None

    terminal_at = str(issue.get("closed_at") or "")
    terminal_time = _parse_timestamp(terminal_at)
    if terminal_time is None:
        raise ValueError("closed_issue_missing_closed_at")

    eligible_prs: list[Mapping[str, Any]] = []
    for pr in merged_prs:
        merged_time = _parse_timestamp(str(pr.get("merged_at") or ""))
        if merged_time is None or merged_time > terminal_time:
            continue
        eligible_prs.append(pr)

    issue_number = int(issue.get("number") or 0)
    changed_files = sorted({
        str(path) for pr in eligible_prs for path in pr.get("changed_files", ()) if str(path)
    })
    check_rows = sorted({
        (str(name), str(state)) for pr in eligible_prs for name, state in pr.get("checks", ())
    })
    refs = [f"issue:{issue_number}:closed@{terminal_at}"]
    for pr in eligible_prs:
        refs.append(f"pr:{int(pr['number'])}@{str(pr.get('merge_commit_sha') or '')}")

    return {
        "terminal_state": ("CLOSED_WITH_MERGED_PR" if eligible_prs else "CLOSED_WITHOUT_MERGED_PR"),
        "terminal_at": terminal_at,
        "evidence_refs": refs,
        "details": {
            "merged_prs": [
                {
                    "number": int(pr["number"]),
                    "merge_commit_sha": str(pr.get("merge_commit_sha") or ""),
                    "head_sha": str(pr.get("head_sha") or ""),
                    "merged_at": str(pr.get("merged_at") or ""),
                }
                for pr in eligible_prs
            ],
            "changed_files": changed_files,
            "checks": [{"name": name, "state": state} for name, state in check_rows],
        },
    }


def _snapshot_from_capture_payload(payload: Mapping[str, Any]) -> TaskSnapshot:
    body = gzip.decompress(
        base64.b64decode(str(payload["body_gzip_base64"]).encode("ascii"))
    ).decode("utf-8")
    return TaskSnapshot.create(
        repository=str(payload["repository"]),
        issue_number=int(payload["issue_number"]),
        created_at=str(payload["created_at"]),
        captured_at=str(payload["captured_at"]),
        issue_updated_at=str(payload["issue_updated_at"]),
        title=str(payload["title"]),
        body=body,
        pre_implementation_revision=str(payload["pre_implementation_revision"]),
        default_branch=str(payload["default_branch"]),
        source_event_id=str(payload["source_event_id"]),
    )


def _frozen_receipt_hashes(
    binding: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    rows = binding.get("frozen_receipts")
    if not isinstance(rows, Mapping) or set(rows) != set(FROZEN_RECEIPT_SHA256S):
        raise ValueError("frozen_receipt_binding_set_mismatch")
    actual: dict[str, str] = {}
    declared: dict[str, str] = {}
    for name in FROZEN_RECEIPT_SHA256S:
        row = rows.get(name)
        if not isinstance(row, Mapping):
            raise ValueError(f"frozen_receipt_binding_invalid:{name}")
        path = Path(str(row.get("path") or ""))
        if not path.is_file():
            raise ValueError(f"frozen_receipt_missing:{name}:{path}")
        actual[name] = _sha256_file(path)
        declared[name] = str(row.get("sha256") or "")
    return actual, declared


def _load_binding(path: Path, *, require_activation: bool = True) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "nexus.hybrid_replication.live_binding.v1":
        raise ValueError("live_binding_schema_mismatch")
    if require_activation and payload.get("activation_state") != "AUTOMATIC_CAPTURE_READY":
        raise ValueError("live_binding_not_activated")
    if require_activation:
        actual_receipts, declared_receipts = _frozen_receipt_hashes(payload)
        if actual_receipts != FROZEN_RECEIPT_SHA256S:
            raise ValueError("frozen_receipt_physical_identity_drift")
        if declared_receipts != FROZEN_RECEIPT_SHA256S:
            raise ValueError("frozen_receipt_declared_identity_drift")
        d0 = payload.get("d0") or {}
        if str(d0.get("implementation_sha256") or "") != D0_IMPLEMENTATION_SHA256:
            raise ValueError("d0_declared_identity_drift")
        if str(d0.get("freeze_sha256") or "") != D0_FREEZE_SHA256:
            raise ValueError("d0_freeze_declared_identity_drift")
        if _sha256_file(Path(str(d0.get("implementation_path") or ""))) != D0_IMPLEMENTATION_SHA256:
            raise ValueError("d0_implementation_hash_drift")
        if _sha256_file(Path(str(d0.get("freeze_path") or ""))) != D0_FREEZE_SHA256:
            raise ValueError("d0_freeze_hash_drift")
        online = payload.get("strong_online") or {}
        provider = str(online.get("provider") or "")
        if provider == "agy":
            if str(online.get("requested_model") or "") != EXACT_AGY_MODEL:
                raise ValueError("agy_requested_model_identity_drift")
            if str(online.get("execution_generation") or "") != "AGY_GEMINI_3_8_FLASH_MEDIUM_V1":
                raise ValueError("agy_execution_generation_identity_drift")
            resolve_canonical_agy_dispatch_path(payload)
        elif provider == "codex" or "codex_executable_sha256" in online:
            if str(online.get("codex_executable_sha256") or "") != CODEX_EXECUTABLE_SHA256:
                raise ValueError("codex_declared_executable_identity_drift")
        else:
            raise ValueError("strong_online_provider_identity_missing")
    return payload


def build_identity_preflight_receipt(
    *,
    d0_sha256: str,
    d0_freeze_sha256: str,
    frozen_receipt_sha256s: Mapping[str, str],
    declared_frozen_receipt_sha256s: Mapping[str, str],
    codex_cli: str,
    previous_codex_cli: str,
    codex_executable_sha256: str,
    expected_codex_executable_sha256: str,
    jev_requested_model: str,
    jev_resolved_model: str,
    expected_jev_resolved_model: str,
    jev_status: str,
    jev_usage: Mapping[str, Any],
    jev_latency_ms: float,
    created_at_utc: str,
) -> dict[str, Any]:
    generation_change = codex_cli != previous_codex_cli
    provider_drift = jev_resolved_model != expected_jev_resolved_model
    frozen_receipts_match = (
        dict(frozen_receipt_sha256s) == FROZEN_RECEIPT_SHA256S
        and dict(declared_frozen_receipt_sha256s) == FROZEN_RECEIPT_SHA256S
    )
    codex_identity_match = (
        codex_executable_sha256 == CODEX_EXECUTABLE_SHA256
        and expected_codex_executable_sha256 == CODEX_EXECUTABLE_SHA256
    )
    activation_allowed = (
        d0_sha256 == D0_IMPLEMENTATION_SHA256
        and d0_freeze_sha256 == D0_FREEZE_SHA256
        and frozen_receipts_match
        and codex_identity_match
        and jev_status == "VALID"
        and not provider_drift
    )
    receipt = {
        "schema": "nexus.hybrid_replication.identity_preflight.v2",
        "created_at_utc": created_at_utc,
        "d0_implementation_sha256": d0_sha256,
        "d0_freeze_sha256": d0_freeze_sha256,
        "frozen_receipt_sha256s": dict(frozen_receipt_sha256s),
        "declared_frozen_receipt_sha256s": dict(declared_frozen_receipt_sha256s),
        "expected_frozen_receipt_sha256s": dict(FROZEN_RECEIPT_SHA256S),
        "frozen_receipts_match": frozen_receipts_match,
        "codex_cli": codex_cli,
        "previous_codex_cli": previous_codex_cli,
        "codex_executable_sha256": codex_executable_sha256,
        "expected_codex_executable_sha256": expected_codex_executable_sha256,
        "codex_identity_match": codex_identity_match,
        "execution_generation_change": generation_change,
        "jev_requested_model": jev_requested_model,
        "jev_resolved_model": jev_resolved_model,
        "expected_jev_resolved_model": expected_jev_resolved_model,
        "provider_identity_drift": provider_drift,
        "jev_status": jev_status,
        "jev_usage": dict(jev_usage),
        "jev_latency_ms": float(jev_latency_ms),
        "activation_allowed": activation_allowed,
        "status": (
            "PASS_NEW_EXECUTION_GENERATION"
            if activation_allowed and generation_change
            else "PASS_SAME_EXECUTION_GENERATION"
            if activation_allowed
            else "BLOCKED_IDENTITY_OR_PROVIDER_DRIFT"
        ),
    }
    receipt["receipt_sha256"] = _sha256_bytes(_canonical_bytes(receipt))
    return receipt


def build_agy_identity_preflight_receipt(
    *,
    d0_sha256: str,
    d0_freeze_sha256: str,
    frozen_receipt_sha256s: Mapping[str, str],
    declared_frozen_receipt_sha256s: Mapping[str, str],
    agy_dispatch_sha256: str,
    expected_agy_dispatch_sha256: str,
    requested_provider: str,
    requested_model: str,
    execution_generation: str,
    previous_execution_generation: str,
    jev_requested_model: str,
    jev_resolved_model: str,
    expected_jev_resolved_model: str,
    jev_status: str,
    jev_usage: Mapping[str, Any],
    jev_latency_ms: float,
    created_at_utc: str,
) -> dict[str, Any]:
    frozen_receipts_match = (
        dict(frozen_receipt_sha256s) == FROZEN_RECEIPT_SHA256S
        and dict(declared_frozen_receipt_sha256s) == FROZEN_RECEIPT_SHA256S
    )
    transport_identity_match = (
        agy_dispatch_sha256 == CANONICAL_AGY_DISPATCH_SHA256
        and expected_agy_dispatch_sha256 == CANONICAL_AGY_DISPATCH_SHA256
    )
    strong_online_identity_match = (
        requested_provider == "agy"
        and requested_model == EXACT_AGY_MODEL
        and execution_generation == "AGY_GEMINI_3_8_FLASH_MEDIUM_V1"
    )
    provider_drift = jev_resolved_model != expected_jev_resolved_model
    generation_change = execution_generation != previous_execution_generation
    activation_allowed = (
        d0_sha256 == D0_IMPLEMENTATION_SHA256
        and d0_freeze_sha256 == D0_FREEZE_SHA256
        and frozen_receipts_match
        and transport_identity_match
        and strong_online_identity_match
        and jev_status == "VALID"
        and not provider_drift
    )
    receipt = {
        "schema": "nexus.hybrid_replication.identity_preflight.v3",
        "created_at_utc": created_at_utc,
        "d0_implementation_sha256": d0_sha256,
        "d0_freeze_sha256": d0_freeze_sha256,
        "frozen_receipt_sha256s": dict(frozen_receipt_sha256s),
        "declared_frozen_receipt_sha256s": dict(declared_frozen_receipt_sha256s),
        "expected_frozen_receipt_sha256s": dict(FROZEN_RECEIPT_SHA256S),
        "frozen_receipts_match": frozen_receipts_match,
        "strong_online_provider": requested_provider,
        "strong_online_requested_model": requested_model,
        "execution_generation": execution_generation,
        "previous_execution_generation": previous_execution_generation,
        "execution_generation_change": generation_change,
        "agy_dispatch_sha256": agy_dispatch_sha256,
        "expected_agy_dispatch_sha256": expected_agy_dispatch_sha256,
        "transport_identity_match": transport_identity_match,
        "strong_online_identity_match": strong_online_identity_match,
        "jev_requested_model": jev_requested_model,
        "jev_resolved_model": jev_resolved_model,
        "expected_jev_resolved_model": expected_jev_resolved_model,
        "provider_identity_drift": provider_drift,
        "jev_status": jev_status,
        "jev_usage": dict(jev_usage),
        "jev_latency_ms": float(jev_latency_ms),
        "activation_allowed": activation_allowed,
        "status": (
            "PASS_NEW_EXECUTION_GENERATION"
            if activation_allowed and generation_change
            else "PASS_SAME_EXECUTION_GENERATION"
            if activation_allowed
            else "BLOCKED_IDENTITY_OR_PROVIDER_DRIFT"
        ),
    }
    receipt["receipt_sha256"] = _sha256_bytes(_canonical_bytes(receipt))
    return receipt


def _repo_root(repository: str, binding: Mapping[str, Any]) -> Path:
    roots = dict(DEFAULT_REPO_ROOTS)
    roots.update(binding.get("repo_roots") or {})
    value = roots.get(repository)
    if not value:
        raise ValueError(f"repository_root_unbound:{repository}")
    path = Path(value)
    if not (path / ".git").exists():
        raise ValueError(f"repository_root_missing:{repository}:{path}")
    return path


def _git(repo: Path, *args: str, timeout: float = 60) -> str:
    cp = _run(["git", *args], cwd=repo, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(f"git_failed:{' '.join(args)}:{cp.stderr.strip()}")
    return cp.stdout


def _revision_exists(repo: Path, revision: str) -> None:
    _git(repo, "cat-file", "-e", f"{revision}^{{tree}}")


def _load_d0(binding: Mapping[str, Any], repo: Path) -> tuple[Any, Mapping[str, Any]]:
    d0 = binding["d0"]
    path = Path(str(d0["implementation_path"]))
    freeze_path = Path(str(d0["freeze_path"]))
    expected = str(d0["implementation_sha256"])
    if expected != D0_IMPLEMENTATION_SHA256:
        raise ValueError("unexpected_d0_identity")
    if _sha256_file(path) != expected:
        raise ValueError("d0_implementation_hash_drift")
    if str(d0.get("freeze_sha256") or "") != D0_FREEZE_SHA256:
        raise ValueError("unexpected_d0_freeze_identity")
    if _sha256_file(freeze_path) != D0_FREEZE_SHA256:
        raise ValueError("d0_freeze_hash_drift")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if str(freeze.get("implementation_sha256")) != expected:
        raise ValueError("d0_freeze_identity_mismatch")

    spec = importlib.util.spec_from_file_location("nexus_hybrid_replication_d0_v2", path)
    if spec is None or spec.loader is None:
        raise ValueError("d0_import_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    setattr(module, "REPO", repo)
    for name in ("FILE_CACHE", "GREP_CACHE", "LOG_CACHE", "SHOW_NAMES_CACHE"):
        getattr(module, name).clear()
    return module, freeze


def _rank_candidates(
    *,
    snapshot: TaskSnapshot,
    repo: Path,
    binding: Mapping[str, Any],
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    module, freeze = _load_d0(binding, repo)
    ranked, _score, why, _query = module.rank_task(
        snapshot.pre_implementation_revision,
        f"ISSUE #{snapshot.issue_number}\nTITLE: {snapshot.title}\n\n{snapshot.body}",
        freeze["weights"],
    )
    evidence = {path: tuple(str(item) for item in why.get(path, ())[:12]) for path in ranked}
    return tuple(ranked), evidence


def _dependency_target_path(snapshot: TaskSnapshot) -> str | None:
    text = f"{snapshot.title}\n{snapshot.body}"
    match = re.search(
        r"perform\s+dependency\s+discovery\s+for\s+[\x60'\"]?([^\x60'\"\s]+\.py)[\x60'\"]?",
        text,
        re.IGNORECASE,
    )
    return None if not match else match.group(1).lstrip("./")


def _dependency_discovery(
    *,
    snapshot: TaskSnapshot,
    repo: Path,
) -> dict[str, Any] | None:
    target = _dependency_target_path(snapshot)
    if not target:
        return None
    cp = _run(
        ["git", "show", f"{snapshot.pre_implementation_revision}:{target}"],
        cwd=repo,
        timeout=30,
    )
    if cp.returncode != 0:
        return None
    try:
        tree = ast.parse(cp.stdout)
    except SyntaxError:
        return None

    imports: list[str] = []
    public: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                public.append(node.name)

    module_name = target[:-3].replace("/", ".")
    grep = _run(
        [
            "git",
            "grep",
            "-l",
            "-E",
            rf"(from[[:space:]]+{re.escape(module_name)}[[:space:]]+import|"
            rf"import[[:space:]]+{re.escape(module_name)}([[:space:]]|$))",
            snapshot.pre_implementation_revision,
            "--",
            "*.py",
        ],
        cwd=repo,
        timeout=30,
    )
    reverse = []
    if grep.returncode in (0, 1):
        for line in grep.stdout.splitlines():
            path = line.split(":", 1)[-1] if ":" in line else line
            if path and path != target and path not in reverse:
                reverse.append(path)

    receipt = {
        "schema": "nexus.hybrid_replication.deterministic_dependency_closure.v1",
        "task_key": snapshot.task_key,
        "source_revision": snapshot.pre_implementation_revision,
        "target": target,
        "direct_imported_modules": sorted(set(imports)),
        "repository_files_directly_importing": sorted(reverse),
        "public_top_level_symbols": sorted(set(public)),
        "verifier_compatible": True,
        "model_calls": 0,
    }
    receipt["receipt_sha256"] = _sha256_bytes(_canonical_bytes(receipt))
    return receipt


def _jev_key(binding: Mapping[str, Any]) -> str:
    command = tuple(str(item) for item in binding["jev"].get("credential_command", ()))
    if not command:
        raise RuntimeError("jev_credential_command_unbound")
    cp = _run(command, timeout=15)
    if cp.returncode != 0 or not cp.stdout.strip():
        raise RuntimeError("jev_credential_unavailable")
    return cp.stdout.strip()


def _valid_probability_distribution(probabilities: Mapping[str, Any]) -> bool:
    if not probabilities:
        return False
    try:
        values = [float(value) for value in probabilities.values()]
    except (TypeError, ValueError):
        return False
    return (
        len(values) == len(probabilities)
        and all(0.0 <= value <= 1.0 for value in values)
        and abs(sum(values) - 1.0) <= 0.03
    )


def _jev_request(
    *,
    snapshot: TaskSnapshot,
    packet: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> tuple[dict[str, Any], int, float]:
    catalog = list(packet["candidate_catalog"])
    criteria = {
        item["id"]: (
            f"Candidate file: {item['path']}. Admitted deterministic evidence: "
            + ("; ".join(item["evidence"]) if item["evidence"] else "bounded candidate provenance")
        )
        for item in catalog
    }
    criteria["ESCALATE"] = (
        "No single supplied candidate is adequately supported, or evidence is too "
        "ambiguous to choose safely."
    )
    payload = {
        "model": str(binding["jev"]["requested_model"]),
        "state": {
            "boundary": (
                "Choose only among supplied candidate IDs. Candidate evidence is "
                "advisory/incomplete; confidence cannot establish evidence sufficiency or absence."
            ),
            "candidate_catalog": catalog,
            "task_key": snapshot.task_key,
            "source_revision": snapshot.pre_implementation_revision,
            "task_contract_text": (
                f"ISSUE #{snapshot.issue_number}\nTITLE: {snapshot.title}\n\n{snapshot.body}"
            ),
        },
        "questions": {
            "file_choice": {
                "type": "choice",
                "instructions": (
                    "Choose the ONE supplied candidate file most likely to require "
                    "modification for this task. Use only supplied candidate IDs. "
                    "Do not invent a path. If no single candidate is adequately supported "
                    "or evidence is too ambiguous, choose ESCALATE."
                ),
                "criteria": criteria,
            }
        },
    }

    key = _jev_key(binding)
    attempts: list[dict[str, Any]] = []
    out: dict[str, Any] | None = None
    total_wall = 0.0
    for attempt in range(1, 3):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        endpoint = str(binding["jev"]["endpoint"])
        if endpoint != JEV_ENDPOINT:
            raise ValueError("jev_endpoint_identity_drift")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
            },
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=45) as response:  # nosec B310
                out = json.loads(response.read())
            wall = time.perf_counter() - started
            total_wall += wall
            attempts.append({"attempt": attempt, "status": "SUCCESS", "latency_ms": wall * 1000})
            break
        except urllib.error.HTTPError as exc:
            wall = time.perf_counter() - started
            total_wall += wall
            body = exc.read().decode("utf-8", "replace")[:300]
            attempts.append({
                "attempt": attempt,
                "status": f"HTTP_{exc.code}",
                "latency_ms": wall * 1000,
                "detail": body,
            })
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except Exception as exc:
            wall = time.perf_counter() - started
            total_wall += wall
            attempts.append({
                "attempt": attempt,
                "status": "NETWORK_FAILURE",
                "latency_ms": wall * 1000,
                "detail": str(exc)[:300],
            })

    if out is None:
        return (
            {
                "schema": "nexus.hybrid_replication.jev_live_raw.v1",
                "status": "PROVIDER_FAILURE",
                "attempts": attempts,
                "request_sha256": _sha256_bytes(_canonical_bytes(payload)),
            },
            max(0, len(attempts) - 1),
            total_wall,
        )

    ans = (out.get("answers") or {}).get("file_choice") or {}
    probs = ans.get("probabilities") or {}
    probabilities_valid = _valid_probability_distribution(probs)
    ordered = (
        sorted(
            ((str(k), float(v)) for k, v in probs.items()),
            key=lambda item: (-item[1], item[0]),
        )
        if probabilities_valid
        else []
    )
    choice = str(ans.get("choice") or "")
    valid = (
        out.get("model") == binding["jev"]["resolved_model"]
        and ans.get("type") == "choice"
        and choice in criteria
        and set(probs) == set(criteria)
        and probabilities_valid
        and bool(ordered)
        and choice == ordered[0][0]
        and isinstance(out.get("usage"), dict)
    )
    top = float(probs.get(choice, 0.0)) if choice in probs else 0.0
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    raw = {
        "schema": "nexus.hybrid_replication.jev_live_raw.v1",
        "status": "VALID" if valid else "INVALID_RESPONSE",
        "requested_model": binding["jev"]["requested_model"],
        "resolved_model": out.get("model"),
        "choice": choice,
        "confidence": ans.get("confidence"),
        "top_probability": top,
        "second_probability": second,
        "margin": top - second,
        "probabilities": probs,
        "usage": out.get("usage"),
        "attempts": attempts,
        "request_sha256": _sha256_bytes(_canonical_bytes(payload)),
        "response_sha256": _sha256_bytes(_canonical_bytes(out)),
    }
    return raw, max(0, len(attempts) - 1), total_wall


def _codex_usage(events: str) -> dict[str, Any]:
    usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
    }
    turns = 0
    errors: list[dict[str, Any]] = []
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            turns += 1
            row = event.get("usage") or {}
            for key in usage:
                usage[key] += int(row.get(key, 0) or 0)
        if event.get("type") in {"error", "turn.failed"}:
            errors.append(event)
    return {"usage": usage, "turns": turns, "errors": errors}


def _export_revision(repo: Path, revision: str, target: Path) -> None:
    cp = subprocess.run(  # nosec B603
        ["/usr/bin/git", "archive", "--format=tar", revision],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"git_archive_failed:{cp.stderr.decode('utf-8', 'replace')[:300]}")
    with tarfile.open(fileobj=io.BytesIO(cp.stdout), mode="r:") as archive:
        archive.extractall(target, filter="data")


def _run_codex(
    *,
    repo: Path,
    revision: str,
    prompt: str,
    schema: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> tuple[dict[str, Any], float]:
    online = binding["strong_online"]
    binary = str(online["codex_binary"])
    version = _run([binary, "--version"], timeout=15)
    if version.returncode != 0:
        raise RuntimeError("codex_version_unavailable")
    if version.stdout.strip() != str(online["codex_cli"]):
        raise RuntimeError(
            f"codex_cli_generation_drift:{version.stdout.strip()}:{online['codex_cli']}"
        )
    executable = Path(str(online["codex_executable_path"]))
    if _sha256_file(executable) != str(online["codex_executable_sha256"]):
        raise RuntimeError("codex_executable_hash_drift")

    with tempfile.TemporaryDirectory(prefix="nexus-hybrid-replication-") as temp:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        _export_revision(repo, revision, source)
        schema_path = root / "schema.json"
        output_path = root / "last.json"
        schema_path.write_text(json.dumps(schema, sort_keys=True), encoding="utf-8")
        cmd = [
            binary,
            "--no-daemon",
            "exec",
            "-m",
            str(online["requested_model"]),
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--json",
            "-s",
            "read-only",
            "-C",
            str(source),
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            prompt,
        ]
        started = time.perf_counter()
        cp = _run(cmd, timeout=300)
        wall = time.perf_counter() - started
        parsed = _codex_usage(cp.stdout)
        try:
            result = json.loads(output_path.read_text(encoding="utf-8"))
            parse_error = None
        except Exception as exc:
            result = {}
            parse_error = f"{type(exc).__name__}:{exc}"
        return (
            {
                "schema": "nexus.hybrid_replication.strong_online_live_raw.v1",
                "status": "VALID" if cp.returncode == 0 and result else "INVALID",
                "requested_model": online["requested_model"],
                "resolved_model": online["requested_model"],
                "codex_cli": version.stdout.strip(),
                "codex_executable_sha256": _sha256_file(executable),
                "returncode": cp.returncode,
                "wall_time_seconds": wall,
                "usage": parsed["usage"],
                "observable_turns": parsed["turns"],
                "error_events": parsed["errors"],
                "parse_error": parse_error,
                "response": result,
                "events_sha256": _sha256_bytes(cp.stdout.encode("utf-8")),
            },
            wall,
        )


def _codex_command_strings(events: str) -> tuple[str, ...]:
    commands: list[str] = []
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        stack: list[Any] = [event]
        while stack:
            item = stack.pop()
            if isinstance(item, Mapping):
                for key, value in item.items():
                    if key in {"command", "cmd"} and isinstance(value, str):
                        commands.append(value)
                    elif isinstance(value, (Mapping, list, tuple)):
                        stack.append(value)
            elif isinstance(item, (list, tuple)):
                stack.extend(item)
    return tuple(commands)


def _run_codex_candidate(
    *,
    repo: Path,
    revision: str,
    prompt: str,
    schema: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> tuple[dict[str, Any], float]:
    online = binding["strong_online"]
    binary = str(online["codex_binary"])
    version = _run([binary, "--version"], timeout=15)
    if version.returncode != 0:
        raise RuntimeError("codex_version_unavailable")
    if version.stdout.strip() != str(online["codex_cli"]):
        raise RuntimeError(
            f"codex_cli_generation_drift:{version.stdout.strip()}:{online['codex_cli']}"
        )
    executable = Path(str(online["codex_executable_path"]))
    actual_executable_sha = _sha256_file(executable)
    if actual_executable_sha != str(online["codex_executable_sha256"]):
        raise RuntimeError("codex_executable_hash_drift")
    if actual_executable_sha != CODEX_EXECUTABLE_SHA256:
        raise RuntimeError("codex_executable_frozen_identity_drift")

    with tempfile.TemporaryDirectory(prefix="nexus-hybrid-replication-c-") as temp:
        root = Path(temp)
        source = root / "source"
        added = _run(
            ["git", "worktree", "add", "--detach", str(source), revision],
            cwd=repo,
            timeout=60,
        )
        if added.returncode != 0:
            raise RuntimeError(f"shadow_worktree_add_failed:{added.stderr.strip()}")
        try:
            schema_path = root / "schema.json"
            output_path = root / "last.json"
            schema_path.write_text(json.dumps(schema, sort_keys=True), encoding="utf-8")
            cmd = [
                binary,
                "--no-daemon",
                "exec",
                "-m",
                str(online["requested_model"]),
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--json",
                "-s",
                "workspace-write",
                "-C",
                str(source),
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                prompt,
            ]
            started = time.perf_counter()
            cp = _run(cmd, timeout=300)
            wall = time.perf_counter() - started
            parsed = _codex_usage(cp.stdout)
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))
                parse_error = None
            except Exception as exc:
                result = {}
                parse_error = f"{type(exc).__name__}:{exc}"

            tracked = _run(
                ["git", "diff", "--name-only", "-z", "HEAD"],
                cwd=source,
                timeout=30,
            )
            untracked = _run(
                ["git", "ls-files", "--others", "--exclude-standard", "-z"],
                cwd=source,
                timeout=30,
            )
            if tracked.returncode != 0 or untracked.returncode != 0:
                raise RuntimeError("shadow_candidate_status_failed")
            changed_files = sorted({
                item for item in (tracked.stdout + untracked.stdout).split("\0") if item
            })
            diff = _run(["git", "diff", "--binary", "HEAD"], cwd=source, timeout=30)
            if diff.returncode != 0:
                raise RuntimeError("shadow_candidate_diff_failed")
            diff_bytes = diff.stdout.encode("utf-8")
            untracked_rows: list[dict[str, Any]] = []
            oversized_untracked: list[str] = []
            for rel in [item for item in untracked.stdout.split("\0") if item]:
                file_path = source / rel
                if not file_path.is_file():
                    continue
                data = file_path.read_bytes()
                row = {
                    "path": rel,
                    "sha256": _sha256_bytes(data),
                    "size": len(data),
                }
                if len(data) <= 5_000_000:
                    row["gzip_base64"] = base64.b64encode(gzip.compress(data, mtime=0)).decode(
                        "ascii"
                    )
                else:
                    oversized_untracked.append(rel)
                untracked_rows.append(row)

            commands = _codex_command_strings(cp.stdout)
            forbidden = sorted({
                command
                for command in commands
                if any(pattern.search(command) for pattern in _FORBIDDEN_SHADOW_COMMANDS)
            })
            protocol_valid = (
                cp.returncode == 0 and bool(result) and not forbidden and not oversized_untracked
            )
            return (
                {
                    "schema": "nexus.hybrid_replication.strong_online_shadow_candidate.v1",
                    "status": "VALID" if protocol_valid else "INVALID",
                    "requested_model": online["requested_model"],
                    "resolved_model": online["requested_model"],
                    "codex_cli": version.stdout.strip(),
                    "codex_executable_sha256": actual_executable_sha,
                    "sandbox": "workspace-write",
                    "returncode": cp.returncode,
                    "wall_time_seconds": wall,
                    "usage": parsed["usage"],
                    "observable_turns": parsed["turns"],
                    "error_events": parsed["errors"],
                    "parse_error": parse_error,
                    "final_response": result,
                    "changed_files": changed_files,
                    "diff_sha256": _sha256_bytes(diff_bytes),
                    "diff_gzip_base64": base64.b64encode(gzip.compress(diff_bytes, mtime=0)).decode(
                        "ascii"
                    ),
                    "untracked_files": untracked_rows,
                    "oversized_untracked_files": oversized_untracked,
                    "observed_commands": list(commands),
                    "forbidden_commands": forbidden,
                    "protocol_valid": protocol_valid,
                    "events_sha256": _sha256_bytes(cp.stdout.encode("utf-8")),
                },
                wall,
            )
        finally:
            _run(
                ["git", "worktree", "remove", "--force", str(source)],
                cwd=repo,
                timeout=60,
            )
            _run(["git", "worktree", "prune"], cwd=repo, timeout=30)


def _b_fallback_prompt(
    snapshot: TaskSnapshot, packet: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    paths = [item["path"] for item in packet["candidate_catalog"]]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ranked_files": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {"type": "string", "enum": paths},
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "reasoning_summary": {"type": "string"},
        },
        "required": ["ranked_files", "confidence", "reasoning_summary"],
    }
    prompt = (
        "You are the strong-Online fallback for the frozen Nexus repository-localization "
        "experiment. Rank only the supplied candidate paths. Do not modify files and do "
        "not invent paths.\n\nTASK:\n"
        + f"{snapshot.title}\n\n{snapshot.body}\n\nCANDIDATE PACKET:\n"
        + json.dumps(packet, ensure_ascii=False, indent=2)
    )
    return prompt, schema


def _expected_agy_dispatch_sha256(binding: Mapping[str, Any] | None) -> str:
    expected = None
    if binding:
        expected = binding.get("agy_dispatch_sha256")
        online = binding.get("strong_online")
        if expected is None and isinstance(online, Mapping):
            expected = online.get("agy_dispatch_sha256") or online.get("dispatch_sha256")
        agy = binding.get("agy")
        if expected is None and isinstance(agy, Mapping):
            expected = agy.get("dispatch_sha256")
    value = str(expected or CANONICAL_AGY_DISPATCH_SHA256)
    if value != CANONICAL_AGY_DISPATCH_SHA256:
        raise RuntimeError(f"agy_dispatch_generation_drift:{value}:{CANONICAL_AGY_DISPATCH_SHA256}")
    return value


def resolve_canonical_agy_dispatch_path(
    binding: Mapping[str, Any] | None = None,
) -> Path:
    expected_sha256 = _expected_agy_dispatch_sha256(binding)
    candidates: list[Path] = []
    if binding:
        if "agy_dispatch_path" in binding:
            candidates.append(Path(str(binding["agy_dispatch_path"])))
        agy = binding.get("agy")
        if isinstance(agy, Mapping) and "dispatch_path" in agy:
            candidates.append(Path(str(agy["dispatch_path"])))
        online = binding.get("strong_online")
        if isinstance(online, Mapping):
            if "agy_dispatch_path" in online:
                candidates.append(Path(str(online["agy_dispatch_path"])))
            elif "dispatch_path" in online:
                candidates.append(Path(str(online["dispatch_path"])))

    env_path = os.getenv("NEXUS_AGY_DISPATCH_PATH")
    if env_path:
        candidates.append(Path(env_path))

    repo_dispatch = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nexus-agy-dispatch"
    candidates.append(repo_dispatch)
    candidates.append(Path.home() / ".local" / "bin" / "nexus-agy-dispatch")

    for cand in candidates:
        cand_expanded = cand.expanduser()
        if cand_expanded.name == "agy":
            raise RuntimeError(
                "raw_agy_forbidden:must invoke configured canonical nexus-agy-dispatch, never raw agy"
            )
        if not cand_expanded.is_file():
            continue
        if cand_expanded.name != CANONICAL_AGY_DISPATCH_NAME:
            raise RuntimeError(f"unexpected_agy_dispatch_name:{cand_expanded.name}")
        actual_sha256 = _sha256_file(cand_expanded)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(f"agy_dispatch_hash_drift:{actual_sha256}:{expected_sha256}")
        return cand_expanded

    raise RuntimeError("canonical_nexus_agy_dispatch_not_found")


_AGY_DENY_RULES = (
    "command(git push)",
    "command(git commit)",
    "command(git fetch)",
    "command(git pull)",
    "command(git clone)",
    "command(git rebase)",
    "command(git merge)",
    "command(git switch)",
    "command(git checkout)",
    "command(git reset)",
    "command(git clean)",
    "command(gh)",
    "command(curl)",
    "command(wget)",
    "command(ssh)",
    "command(scp)",
    "command(rsync)",
)


def _agy_permission_args(cwd: Path, *, mode: str) -> tuple[str, ...]:
    root = str(cwd.resolve())
    args: list[str] = [
        "--temp-command-permissions",
        "--allow",
        f"read_file({root}/**)",
    ]
    if mode == "accept-edits":
        args.extend(["--allow", f"write_file({root}/**)"])
    for rule in _AGY_DENY_RULES:
        args.extend(["--deny", rule])
    return tuple(args)


def poll_agy_operation(
    operation_json: Path,
    *,
    timeout: float = 300.0,
    poll_interval: float = 0.05,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    """Poll operation.json until terminal state is observed or timeout expires.

    Returns (record, timed_out, error_reason).
    """
    deadline = time.monotonic() + timeout
    last_corrupt = False
    while time.monotonic() < deadline:
        if operation_json.is_file():
            try:
                data = json.loads(operation_json.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    status = str(data.get("status") or "")
                    if status in TERMINAL_STATES:
                        return data, False, None
                else:
                    last_corrupt = True
            except (OSError, json.JSONDecodeError):
                last_corrupt = True
        time.sleep(poll_interval)

    if operation_json.is_file():
        try:
            data = json.loads(operation_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                status = str(data.get("status") or "")
                if status in TERMINAL_STATES:
                    return data, False, None
                return data, True, "TIMEOUT"
            return None, False, "MISSING_OR_CORRUPT_JOURNAL"
        except (OSError, json.JSONDecodeError):
            return None, False, "MISSING_OR_CORRUPT_JOURNAL"

    return None, True, "MISSING_OR_CORRUPT_JOURNAL" if last_corrupt else "TIMEOUT"


def evaluate_agy_receipt(
    record: Mapping[str, Any] | None,
    *,
    dispatch_path: Path,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    timed_out: bool = False,
    error_reason: str | None = None,
    wall_time_seconds: float = 0.0,
    schema: str = AGY_RAW_RECEIPT_SCHEMA,
    extra_checks: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stdout_bytes = stdout_path.read_bytes() if (stdout_path and stdout_path.is_file()) else b""
    stderr_bytes = stderr_path.read_bytes() if (stderr_path and stderr_path.is_file()) else b""
    stdout_sha256 = _sha256_bytes(stdout_bytes)
    stderr_sha256 = _sha256_bytes(stderr_bytes)
    output_oversized = (
        len(stdout_bytes) > MAX_AGY_PROVIDER_OUTPUT_BYTES
        or len(stderr_bytes) > MAX_AGY_PROVIDER_OUTPUT_BYTES
    )
    dispatch_sha256 = _sha256_file(dispatch_path) if dispatch_path.is_file() else None

    if dispatch_path.name == "agy":
        status = "UNEXPECTED_TRANSPORT_IDENTITY"
    elif dispatch_sha256 != CANONICAL_AGY_DISPATCH_SHA256:
        status = "UNEXPECTED_TRANSPORT_IDENTITY"
    elif output_oversized:
        status = "OVERSIZED_PROVIDER_OUTPUT_REJECTED"
    elif error_reason == "MISSING_OR_CORRUPT_JOURNAL" or record is None:
        status = "MISSING_OR_CORRUPT_JOURNAL" if not timed_out else "TIMEOUT"
    elif timed_out:
        status = "TIMEOUT"
    else:
        status_val = str(record.get("status") or "")
        observed_provider = str(record.get("observed_provider") or "")
        observed_model = str(record.get("observed_model") or "")
        provider = str(record.get("provider") or "")

        if status_val == "OUTCOME_UNKNOWN":
            status = "OUTCOME_UNKNOWN"
        elif status_val != "COMPLETED":
            status = f"OPERATION_{status_val}"
        elif provider != "agy":
            status = "UNEXPECTED_TRANSPORT_IDENTITY"
        elif observed_provider != "agy":
            status = "PROVIDER_SUBSTITUTION_REJECTED"
        elif observed_model != EXACT_AGY_MODEL:
            status = "MODEL_SUBSTITUTION_REJECTED"
        elif extra_checks and not extra_checks.get("valid", True):
            status = str(extra_checks.get("reason") or "INVALID")
        else:
            status = "VALID"

    usage = (record.get("usage") if record else {}) or {}
    return {
        "schema": schema,
        "status": status,
        "valid": status == "VALID",
        "operation_id": str(record.get("operation_id") or "") if record else "",
        "account_alias_hash": record.get("account_alias_hash") if record else None,
        "rotations": int(record.get("rotations") or 0) if record else 0,
        "failure_kind": record.get("failure_kind") if record else None,
        "provider_session_id": record.get("provider_session_id") if record else None,
        "runtime_revision": record.get("runtime_revision") if record else None,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "stdout_size": len(stdout_bytes),
        "stderr_size": len(stderr_bytes),
        "stdout_gzip_base64": (
            base64.b64encode(gzip.compress(stdout_bytes, mtime=0)).decode("ascii")
            if len(stdout_bytes) <= MAX_AGY_PROVIDER_OUTPUT_BYTES
            else None
        ),
        "stderr_gzip_base64": (
            base64.b64encode(gzip.compress(stderr_bytes, mtime=0)).decode("ascii")
            if len(stderr_bytes) <= MAX_AGY_PROVIDER_OUTPUT_BYTES
            else None
        ),
        "provider_output_oversized": output_oversized,
        "transport_identity": CANONICAL_AGY_DISPATCH_NAME,
        "dispatch_path": str(dispatch_path),
        "dispatch_sha256": dispatch_sha256,
        "requested_model": EXACT_AGY_MODEL,
        "resolved_model": (record.get("observed_model") if record else None) or EXACT_AGY_MODEL,
        "observed_provider": record.get("observed_provider") if record else None,
        "observed_model": record.get("observed_model") if record else None,
        "exit_code": record.get("exit_code") if record else None,
        "wall_time_seconds": wall_time_seconds,
        "usage": usage,
        "usage_observation": ("OBSERVED" if usage else "UNAVAILABLE_NOT_ZERO"),
    }


def seal_shadow_candidate(
    source: Path,
    *,
    allowed_paths: Sequence[str] | None = None,
    max_file_size: int = 5_000_000,
) -> dict[str, Any]:
    tracked = _run(["git", "diff", "--name-only", "-z", "HEAD"], cwd=source, timeout=30)
    untracked = _run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=source,
        timeout=30,
    )
    if tracked.returncode != 0 or untracked.returncode != 0:
        raise RuntimeError("shadow_candidate_status_failed")

    tracked_paths = [item for item in tracked.stdout.split("\0") if item]
    untracked_paths = [item for item in untracked.stdout.split("\0") if item]
    changed_files = sorted(set(tracked_paths + untracked_paths))

    diff = _run(["git", "diff", "--binary", "HEAD"], cwd=source, timeout=30)
    if diff.returncode != 0:
        raise RuntimeError("shadow_candidate_diff_failed")
    diff_bytes = diff.stdout.encode("utf-8")

    untracked_rows: list[dict[str, Any]] = []
    oversized_untracked: list[str] = []
    for rel in untracked_paths:
        file_path = source / rel
        if not file_path.is_file():
            continue
        data = file_path.read_bytes()
        row: dict[str, Any] = {
            "path": rel,
            "sha256": _sha256_bytes(data),
            "size": len(data),
        }
        if len(data) <= max_file_size:
            row["gzip_base64"] = base64.b64encode(gzip.compress(data, mtime=0)).decode("ascii")
        else:
            oversized_untracked.append(rel)
        untracked_rows.append(row)

    out_of_scope: list[str] = []
    allowed_set = set(allowed_paths) if allowed_paths is not None else None
    for path in changed_files:
        if (
            path.startswith(("/", "../"))
            or "/../" in path
            or path == ".git"
            or path.startswith(".git/")
        ):
            out_of_scope.append(path)
        elif allowed_set is not None and path not in allowed_set:
            out_of_scope.append(path)

    return {
        "changed_files": changed_files,
        "diff_sha256": _sha256_bytes(diff_bytes),
        "diff_gzip_base64": base64.b64encode(gzip.compress(diff_bytes, mtime=0)).decode("ascii"),
        "untracked_files": untracked_rows,
        "oversized_untracked_files": oversized_untracked,
        "out_of_scope_paths": sorted(out_of_scope),
        "scope_valid": not out_of_scope and not oversized_untracked,
    }


def _run_agy_dispatch(
    *,
    cwd: Path,
    prompt: str,
    mode: str,
    binding: Mapping[str, Any],
    timeout: int = 300,
    poll_timeout: float = 300.0,
    poll_interval: float = 0.05,
    operation_root: Path | None = None,
) -> tuple[dict[str, Any] | None, float, Path | None, Path | None, bool, str | None, Path]:
    dispatch_path = resolve_canonical_agy_dispatch_path(binding)
    if operation_root is None:
        if "operation_root" in binding:
            operation_root = Path(str(binding["operation_root"]))
        elif (
            "agy" in binding
            and isinstance(binding["agy"], Mapping)
            and "operation_root" in binding["agy"]
        ):
            operation_root = Path(str(binding["agy"]["operation_root"]))
        elif os.getenv("NEXUS_AGY_OPERATION_ROOT"):
            operation_root = Path(os.environ["NEXUS_AGY_OPERATION_ROOT"])
        else:
            operation_root = Path.home() / ".local/state/nexus-agy-operations"

    online = binding.get("strong_online")
    effort = str(online.get("effort") or "medium") if isinstance(online, Mapping) else "medium"
    cmd = [
        str(dispatch_path),
        "--background",
        "--cwd",
        str(cwd),
        "--mode",
        mode,
        "--model",
        EXACT_AGY_MODEL,
        "--effort",
        effort,
        "--timeout",
        str(timeout),
        "--max-calls",
        "1",
        "--operation-root",
        str(operation_root),
        *_agy_permission_args(cwd, mode=mode),
    ]

    started = time.perf_counter()
    cp = _run(cmd, input_text=prompt, timeout=60)
    if cp.returncode != 0:
        wall = time.perf_counter() - started
        return None, wall, None, None, False, f"SPAWN_FAILED:{cp.stderr.strip()}", dispatch_path

    try:
        initial = json.loads(cp.stdout.strip())
        operation_id = str(initial.get("operation_id") or "")
    except Exception:
        wall = time.perf_counter() - started
        return None, wall, None, None, False, "MISSING_OR_CORRUPT_JOURNAL", dispatch_path

    if not operation_id:
        wall = time.perf_counter() - started
        return None, wall, None, None, False, "MISSING_OR_CORRUPT_JOURNAL", dispatch_path

    stdout_path = Path(
        initial.get("stdout_path") or (operation_root / "operations" / operation_id / "stdout.log")
    )
    stderr_path = Path(
        initial.get("stderr_path") or (operation_root / "operations" / operation_id / "stderr.log")
    )
    operation_json = stdout_path.parent / "operation.json"

    effective_poll_timeout = max(
        float(poll_timeout),
        float(timeout) + AGY_PROVIDER_TERMINAL_GRACE_SECONDS,
    )
    record, timed_out, err = poll_agy_operation(
        operation_json,
        timeout=effective_poll_timeout,
        poll_interval=poll_interval,
    )
    wall = time.perf_counter() - started
    return record, wall, stdout_path, stderr_path, timed_out, err, dispatch_path


def _run_agy_b_fallback(
    *,
    repo: Path,
    revision: str,
    prompt: str,
    binding: Mapping[str, Any],
    timeout: int = 300,
    poll_timeout: float = 300.0,
    poll_interval: float = 0.05,
) -> tuple[dict[str, Any], float]:
    with tempfile.TemporaryDirectory(prefix="nexus-hybrid-replication-b-") as temp:
        root = Path(temp)
        source = root / "source"
        added = _run(
            ["git", "worktree", "add", "--detach", str(source), revision],
            cwd=repo,
            timeout=60,
        )
        if added.returncode != 0:
            raise RuntimeError(f"shadow_worktree_add_failed:{added.stderr.strip()}")
        try:
            record, wall, stdout_path, stderr_path, timed_out, err, dispatch_path = (
                _run_agy_dispatch(
                    cwd=source,
                    prompt=prompt,
                    mode="plan",
                    binding=binding,
                    timeout=timeout,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                )
            )
            status_check = _run(["git", "status", "--porcelain=v1"], cwd=source, timeout=30)
            mutated = bool(status_check.stdout.strip())
            extra_checks = None
            if mutated:
                extra_checks = {"valid": False, "reason": "REPOSITORY_MUTATION_REJECTED"}

            receipt = evaluate_agy_receipt(
                record,
                dispatch_path=dispatch_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timed_out=timed_out,
                error_reason=err,
                wall_time_seconds=wall,
                schema=AGY_RAW_RECEIPT_SCHEMA,
                extra_checks=extra_checks,
            )
            receipt["mode"] = "plan"
            receipt["repository_mutated"] = mutated
            return receipt, wall
        finally:
            _run(
                ["git", "worktree", "remove", "--force", str(source)],
                cwd=repo,
                timeout=60,
            )
            _run(["git", "worktree", "prune"], cwd=repo, timeout=30)


def _run_agy_candidate(
    *,
    repo: Path,
    revision: str,
    prompt: str,
    binding: Mapping[str, Any],
    timeout: int = 300,
    poll_timeout: float = 300.0,
    poll_interval: float = 0.05,
    allowed_paths: Sequence[str] | None = None,
) -> tuple[dict[str, Any], float]:
    with tempfile.TemporaryDirectory(prefix="nexus-hybrid-replication-c-") as temp:
        root = Path(temp)
        source = root / "source"
        added = _run(
            ["git", "worktree", "add", "--detach", str(source), revision],
            cwd=repo,
            timeout=60,
        )
        if added.returncode != 0:
            raise RuntimeError(f"shadow_worktree_add_failed:{added.stderr.strip()}")
        try:
            record, wall, stdout_path, stderr_path, timed_out, err, dispatch_path = (
                _run_agy_dispatch(
                    cwd=source,
                    prompt=prompt,
                    mode="accept-edits",
                    binding=binding,
                    timeout=timeout,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                )
            )
            sealing = seal_shadow_candidate(source, allowed_paths=allowed_paths)
            extra_checks = None
            if not sealing["scope_valid"]:
                reason = (
                    "SCOPE_REJECTED"
                    if sealing["out_of_scope_paths"]
                    else "OVERSIZED_ARTIFACT_REJECTED"
                )
                extra_checks = {"valid": False, "reason": reason}
            elif record is not None and isinstance(record.get("observed_changed_paths"), list):
                journal_paths = sorted(str(path) for path in record["observed_changed_paths"])
                if journal_paths != sealing["changed_files"]:
                    extra_checks = {
                        "valid": False,
                        "reason": "JOURNAL_DIFF_MISMATCH",
                    }

            receipt = evaluate_agy_receipt(
                record,
                dispatch_path=dispatch_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timed_out=timed_out,
                error_reason=err,
                wall_time_seconds=wall,
                schema=AGY_SHADOW_CANDIDATE_SCHEMA,
                extra_checks=extra_checks,
            )
            receipt["mode"] = "accept-edits"
            receipt.update(sealing)
            return receipt, wall
        finally:
            _run(
                ["git", "worktree", "remove", "--force", str(source)],
                cwd=repo,
                timeout=60,
            )
            _run(["git", "worktree", "prune"], cwd=repo, timeout=30)


def _complete_token_usage_metrics(
    *usage_records: Mapping[str, Any],
) -> tuple[int | None, int | None, int | None]:
    if not usage_records or any(not usage for usage in usage_records):
        return None, None, None
    input_tokens = sum(int(usage.get("input_tokens", 0) or 0) for usage in usage_records)
    uncached_input_tokens = sum(
        max(
            0,
            int(usage.get("input_tokens", 0) or 0)
            - int(usage.get("cached_input_tokens", 0) or 0),
        )
        for usage in usage_records
    )
    output_tokens = sum(int(usage.get("output_tokens", 0) or 0) for usage in usage_records)
    return input_tokens, uncached_input_tokens, output_tokens


def _c_prompt(snapshot: TaskSnapshot) -> tuple[str, dict[str, Any]]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {
                "type": "string",
                "enum": ["CANDIDATE", "NO_CHANGE", "BLOCKED"],
            },
            "summary": {"type": "string"},
            "risk_notes": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string"},
            },
        },
        "required": ["status", "summary", "risk_notes"],
    }
    prompt = (
        "You are the frozen strong-Online arm for a prospective Nexus engineering "
        "replication. Work only in this isolated captured-base checkout. Implement the "
        "supplied task as a best-effort shadow Candidate while preserving its exact "
        "authority and scope. Do not commit, push, fetch, pull, clone, perform network "
        "requests (gh/curl/wget/ssh), or install dependencies/tools. Do not use future "
        "outcome information (such as future PRs, changed-file lists, CI/check verifiers, "
        "merge commits, or final-worker outcomes). Return only the bounded execution summary "
        "required by the output schema; the harness separately seals the physical diff.\n\n"
        f"TASK KEY: {snapshot.task_key}\n"
        f"SOURCE REVISION: {snapshot.pre_implementation_revision}\n"
        f"TITLE: {snapshot.title}\n\n{snapshot.body}"
    )
    return prompt, schema


def run_frozen_stack(
    snapshot: TaskSnapshot,
    *,
    binding: Mapping[str, Any],
) -> FrozenStackOutcome:
    repo = _repo_root(snapshot.repository, binding)
    _revision_exists(repo, snapshot.pre_implementation_revision)
    family = classify_frozen_task_family(title=snapshot.title, body=snapshot.body)

    if family == "A":
        started = time.perf_counter()
        deterministic = _dependency_discovery(snapshot=snapshot, repo=repo)
        wall = time.perf_counter() - started
        if deterministic is not None:
            raw = RawRouteResult.create(
                route="A",
                provider="deterministic",
                requested_model="",
                resolved_model="",
                model_call_count=0,
                input_tokens=0,
                uncached_input_tokens=0,
                output_tokens=0,
                wall_time_seconds=wall,
                failures=(),
                retries=0,
                fallbacks=(),
                raw_response=deterministic,
            )
            return FrozenStackOutcome(
                stratum="A",
                deterministic_receipt=deterministic,
                candidate_packet=None,
                jev_raw_response=None,
                dm1_decision=None,
                strong_online_raw_response=None,
                raw_result=raw,
            )

    if family == "B":
        ranked, evidence = _rank_candidates(snapshot=snapshot, repo=repo, binding=binding)
        repo_files = set(
            _git(
                repo, "ls-tree", "-r", "--name-only", snapshot.pre_implementation_revision
            ).splitlines()
        )
        literal = tuple(
            path
            for path in extract_literal_paths(f"{snapshot.title}\n{snapshot.body}")
            if path in repo_files
        )
        packet = build_d2_candidate_packet(
            task_key=snapshot.task_key,
            source_revision=snapshot.pre_implementation_revision,
            task_contract=f"{snapshot.title}\n\n{snapshot.body}",
            literal_paths=literal,
            ranked_paths=ranked,
            evidence=evidence,
        )
        if len(packet["candidate_catalog"]) >= 2:
            jev_raw, jev_retries, jev_wall = _jev_request(
                snapshot=snapshot,
                packet=packet,
                binding=binding,
            )
            decision = {
                "choice": jev_raw.get("choice", "ESCALATE"),
                "top_probability": float(jev_raw.get("top_probability") or 0.0),
                "margin": float(jev_raw.get("margin") or 0.0),
                "policy_top_probability_min": DM1_TOP_PROBABILITY_MIN,
                "policy_margin_min": DM1_MARGIN_MIN,
            }
            accepted = (
                jev_raw.get("status") == "VALID"
                and decision["choice"] != "ESCALATE"
                and decision["top_probability"] >= DM1_TOP_PROBABILITY_MIN
                and decision["margin"] >= DM1_MARGIN_MIN
            )
            strong = None
            fallbacks: tuple[str, ...] = ()
            strong_wall = 0.0
            if not accepted:
                prompt, schema = _b_fallback_prompt(snapshot, packet)
                strong, strong_wall = _run_agy_b_fallback(
                    repo=repo,
                    revision=snapshot.pre_implementation_revision,
                    prompt=prompt,
                    binding=binding,
                )
                fallbacks = ("DM1_TO_STRONG_ONLINE",)
            jev_usage = jev_raw.get("usage") or {}
            strong_usage = (strong or {}).get("usage") or {}
            usage_records = (jev_usage,) if accepted else (jev_usage, strong_usage)
            input_tokens, uncached_input_tokens, output_tokens = (
                _complete_token_usage_metrics(*usage_records)
            )
            raw_response = {
                "candidate_packet": packet,
                "jev_raw_response": jev_raw,
                "dm1_decision": decision,
                "strong_online_raw_response": strong,
                "accepted_by_frozen_policy": accepted,
            }
            raw = RawRouteResult.create(
                route="B",
                provider="typesafe" if accepted else "typesafe+agy",
                requested_model=(
                    str(binding["jev"]["requested_model"])
                    if accepted
                    else f"{binding['jev']['requested_model']}+{EXACT_AGY_MODEL}"
                ),
                resolved_model=(
                    str(binding["jev"]["resolved_model"])
                    if accepted
                    else f"{binding['jev']['resolved_model']}+{(strong or {}).get('resolved_model') or (strong or {}).get('observed_model') or EXACT_AGY_MODEL}"
                ),
                model_call_count=1 if accepted else 2,
                input_tokens=input_tokens,
                uncached_input_tokens=uncached_input_tokens,
                output_tokens=output_tokens,
                wall_time_seconds=jev_wall + strong_wall,
                failures=()
                if jev_raw.get("status") == "VALID"
                and (accepted or (strong or {}).get("status") == "VALID")
                else (
                    *(
                        ()
                        if jev_raw.get("status") == "VALID"
                        else (str(jev_raw.get("status") or "JEV_FAILURE"),)
                    ),
                    *(
                        ()
                        if accepted or (strong or {}).get("status") == "VALID"
                        else (str((strong or {}).get("status") or "AGY_FAILURE"),)
                    ),
                ),
                retries=jev_retries,
                fallbacks=fallbacks,
                raw_response=raw_response,
            )
            return FrozenStackOutcome(
                stratum="B",
                deterministic_receipt={
                    "status": "INSUFFICIENT_FOR_TERMINAL_CLOSURE",
                    "d0_implementation_sha256": D0_IMPLEMENTATION_SHA256,
                    "d2_packet_sha256": packet["packet_sha256"],
                },
                candidate_packet=packet,
                jev_raw_response=jev_raw,
                dm1_decision=decision,
                strong_online_raw_response=strong,
                raw_result=raw,
            )

    prompt, schema = _c_prompt(snapshot)
    strong, wall = _run_agy_candidate(
        repo=repo,
        revision=snapshot.pre_implementation_revision,
        prompt=prompt,
        binding=binding,
    )
    usage = strong.get("usage") or {}
    input_tokens, uncached_input_tokens, output_tokens = _complete_token_usage_metrics(usage)
    raw = RawRouteResult.create(
        route="C",
        provider="agy",
        requested_model=EXACT_AGY_MODEL,
        resolved_model=str(
            strong.get("resolved_model") or strong.get("observed_model") or EXACT_AGY_MODEL
        ),
        model_call_count=1,
        input_tokens=input_tokens,
        uncached_input_tokens=uncached_input_tokens,
        output_tokens=output_tokens,
        wall_time_seconds=wall,
        failures=()
        if strong.get("status") == "VALID"
        else (str(strong.get("status") or "AGY_FAILURE"),),
        retries=0,
        fallbacks=(),
        raw_response=strong,
    )
    return FrozenStackOutcome(
        stratum="C",
        deterministic_receipt={
            "status": "INSUFFICIENT_FOR_TERMINAL_CLOSURE",
            "family_probe": family,
        },
        candidate_packet=None,
        jev_raw_response=None,
        dm1_decision=None,
        strong_online_raw_response=strong,
        raw_result=raw,
    )


def _gh_json(*args: str) -> Any:
    cp = subprocess.run(  # nosec B603 B607
        ["gh", "api", *args],
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"gh_api_failed:{cp.returncode}:{cp.stderr.strip()}")
    return json.loads(cp.stdout)


def _gh_list(path: str, *, accept: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 11):
        sep = "&" if "?" in path else "?"
        args = ["-X", "GET"]
        if accept:
            args.extend(["-H", f"Accept: {accept}"])
        args.append(f"{path}{sep}per_page=100&page={page}")
        payload = _gh_json(*args)
        if not isinstance(payload, list):
            raise RuntimeError("github_paged_response_not_list")
        rows.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return rows
    raise RuntimeError("github_pagination_exceeds_bound")


def _check_runs_until(
    repository: str,
    head_sha: str,
    terminal_time: dt.datetime,
) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for page in range(1, 11):
        payload = _gh_json(
            "-X",
            "GET",
            f"repos/{repository}/commits/{head_sha}/check-runs?per_page=100&page={page}",
        )
        batch = payload.get("check_runs", []) if isinstance(payload, Mapping) else []
        if not isinstance(batch, list):
            raise RuntimeError("check_runs_response_not_list")
        for item in batch:
            if not isinstance(item, Mapping):
                continue
            completed_time = _parse_timestamp(str(item.get("completed_at") or ""))
            if completed_time is None or completed_time > terminal_time:
                continue
            rows.append((
                str(item.get("name") or ""),
                str(item.get("conclusion") or item.get("status") or ""),
            ))
        if len(batch) < 100:
            return tuple(rows)
    raise RuntimeError("check_runs_pagination_exceeds_bound")


def _resolve_ground_truth_from_state(state: Mapping[str, Any]) -> dict[str, Any] | None:
    if state.get("phase") != "RAW_SEALED":
        raise ValueError("ground_truth_requires_raw_sealed")
    snapshot = state.get("snapshot") or {}
    repository = str(snapshot.get("repository") or "")
    issue_number = int(snapshot.get("issue_number") or 0)
    if not repository or not issue_number:
        raise ValueError("task_state_identity_missing")
    issue = _gh_json(f"repos/{repository}/issues/{issue_number}")
    if str(issue.get("state") or "") != "closed":
        return None
    terminal_at = str(issue.get("closed_at") or "")
    terminal_time = _parse_timestamp(terminal_at)
    if terminal_time is None:
        raise ValueError("closed_issue_missing_closed_at")

    timeline = _gh_list(
        f"repos/{repository}/issues/{issue_number}/timeline",
        accept="application/vnd.github+json",
    )
    pr_numbers: set[int] = set()
    for item in timeline:
        if item.get("event") != "cross-referenced":
            continue
        event_time = _parse_timestamp(str(item.get("created_at") or ""))
        if event_time is not None and event_time > terminal_time:
            continue
        source = item.get("source") or {}
        source_issue = source.get("issue") if isinstance(source, Mapping) else {}
        if not isinstance(source_issue, Mapping) or "pull_request" not in source_issue:
            continue
        if str(source_issue.get("repository_url") or "") != (
            f"https://api.github.com/repos/{repository}"
        ):
            continue
        number = source_issue.get("number")
        if isinstance(number, int):
            pr_numbers.add(number)

    merged: list[dict[str, Any]] = []
    for number in sorted(pr_numbers):
        pr = _gh_json(f"repos/{repository}/pulls/{number}")
        merged_at = str(pr.get("merged_at") or "")
        merged_time = _parse_timestamp(merged_at)
        if merged_time is None or merged_time > terminal_time:
            continue
        files = _gh_list(f"repos/{repository}/pulls/{number}/files")
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        merged.append({
            "number": number,
            "merge_commit_sha": str(pr.get("merge_commit_sha") or ""),
            "head_sha": head_sha,
            "merged_at": merged_at,
            "changed_files": tuple(
                str(item.get("filename") or "") for item in files if item.get("filename")
            ),
            "checks": _check_runs_until(repository, head_sha, terminal_time),
        })
    return resolve_ground_truth_payload(issue=issue, merged_prs=tuple(merged))


def _identity_preflight_main(binding_path: Path) -> int:
    binding = _load_binding(binding_path, require_activation=False)
    d0 = binding["d0"]
    d0_path = Path(str(d0["implementation_path"]))
    d0_freeze_path = Path(str(d0["freeze_path"]))
    d0_sha = _sha256_file(d0_path)
    d0_freeze_sha = _sha256_file(d0_freeze_path)
    frozen_actual, frozen_declared = _frozen_receipt_hashes(binding)

    snapshot = TaskSnapshot.create(
        repository="synthetic/preflight",
        issue_number=0,
        created_at="1970-01-01T00:00:00Z",
        captured_at="1970-01-01T00:00:00Z",
        issue_updated_at="1970-01-01T00:00:00Z",
        title="Hybrid replication identity preflight",
        body="Choose among a sealed synthetic candidate set. No scored dataset outcome.",
        pre_implementation_revision="0" * 40,
        default_branch="none",
        source_event_id="activation-preflight",
    )
    packet = build_d2_candidate_packet(
        task_key=snapshot.task_key,
        source_revision=snapshot.pre_implementation_revision,
        task_contract=f"{snapshot.title}\n\n{snapshot.body}",
        literal_paths=(),
        ranked_paths=(
            "synthetic/alpha.py",
            "synthetic/beta.py",
            "synthetic/gamma.py",
        ),
        evidence={
            "synthetic/alpha.py": ("synthetic_identity_probe",),
            "synthetic/beta.py": ("synthetic_identity_probe",),
            "synthetic/gamma.py": ("synthetic_identity_probe",),
        },
    )
    jev_raw, retries, wall = _jev_request(
        snapshot=snapshot,
        packet=packet,
        binding=binding,
    )

    online = binding.get("strong_online") or {}
    provider = str(online.get("provider") or "")
    created_at_utc = (
        dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    if provider == "agy":
        dispatch_path = resolve_canonical_agy_dispatch_path(binding)
        receipt = build_agy_identity_preflight_receipt(
            d0_sha256=d0_sha,
            d0_freeze_sha256=d0_freeze_sha,
            frozen_receipt_sha256s=frozen_actual,
            declared_frozen_receipt_sha256s=frozen_declared,
            agy_dispatch_sha256=_sha256_file(dispatch_path),
            expected_agy_dispatch_sha256=str(
                online.get("agy_dispatch_sha256")
                or binding.get("agy_dispatch_sha256")
                or CANONICAL_AGY_DISPATCH_SHA256
            ),
            requested_provider=provider,
            requested_model=str(online.get("requested_model") or ""),
            execution_generation=str(online.get("execution_generation") or ""),
            previous_execution_generation=str(online.get("previous_execution_generation") or ""),
            jev_requested_model=str(binding["jev"]["requested_model"]),
            jev_resolved_model=str(jev_raw.get("resolved_model") or ""),
            expected_jev_resolved_model=str(binding["jev"]["resolved_model"]),
            jev_status=str(jev_raw.get("status") or ""),
            jev_usage=dict(jev_raw.get("usage") or {}),
            jev_latency_ms=wall * 1000,
            created_at_utc=created_at_utc,
        )
    else:
        binary = str(online["codex_binary"])
        version = _run([binary, "--version"], timeout=15)
        if version.returncode != 0:
            raise RuntimeError("codex_version_unavailable")
        executable = Path(str(online["codex_executable_path"]))
        executable_sha = _sha256_file(executable)
        receipt = build_identity_preflight_receipt(
            d0_sha256=d0_sha,
            d0_freeze_sha256=d0_freeze_sha,
            frozen_receipt_sha256s=frozen_actual,
            declared_frozen_receipt_sha256s=frozen_declared,
            codex_cli=version.stdout.strip(),
            previous_codex_cli=str(online["previous_codex_cli"]),
            codex_executable_sha256=executable_sha,
            expected_codex_executable_sha256=str(online["codex_executable_sha256"]),
            jev_requested_model=str(binding["jev"]["requested_model"]),
            jev_resolved_model=str(jev_raw.get("resolved_model") or ""),
            expected_jev_resolved_model=str(binding["jev"]["resolved_model"]),
            jev_status=str(jev_raw.get("status") or ""),
            jev_usage=dict(jev_raw.get("usage") or {}),
            jev_latency_ms=wall * 1000,
            created_at_utc=created_at_utc,
        )

    receipt["jev_retries"] = retries
    receipt["jev_request_sha256"] = jev_raw.get("request_sha256")
    receipt["jev_response_sha256"] = jev_raw.get("response_sha256")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["activation_allowed"] else 5


def _stack_main(binding_path: Path) -> int:
    payload = json.load(sys.stdin)
    snapshot = _snapshot_from_capture_payload(payload)
    binding = _load_binding(binding_path)
    outcome = run_frozen_stack(snapshot, binding=binding)
    print(json.dumps(asdict(outcome), ensure_ascii=False, sort_keys=True))
    return 0


def _ground_truth_main() -> int:
    state = json.load(sys.stdin)
    payload = _resolve_ground_truth_from_state(state)
    if payload is None:
        return 3
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("identity-preflight")
    preflight.add_argument("--binding", default=str(DEFAULT_LIVE_BINDING))
    stack = sub.add_parser("stack")
    stack.add_argument("--binding", default=str(DEFAULT_LIVE_BINDING))
    sub.add_parser("ground-truth")
    args = parser.parse_args()
    if args.command == "identity-preflight":
        return _identity_preflight_main(Path(args.binding))
    if args.command == "stack":
        return _stack_main(Path(args.binding))
    return _ground_truth_main()


if __name__ == "__main__":
    raise SystemExit(main())
