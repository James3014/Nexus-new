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

D0_IMPLEMENTATION_SHA256 = "cca215a2de82996c072f958159541a93d58b1482af3430d93f537c58ddafa2f9"
D0_DEFAULT_PATH = Path(
    "/Users/james/workspace/nexus-hardware-lab/local-capability-expansion-v1/"
    "task-localization-v1/d0_v2_develop.py"
)
D0_DEFAULT_FREEZE = D0_DEFAULT_PATH.with_name("D0_V2_FROZEN.json")
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


def resolve_ground_truth_payload(
    *,
    issue: Mapping[str, Any],
    merged_prs: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if str(issue.get("state") or "") != "closed":
        return None

    issue_number = int(issue.get("number") or 0)
    changed_files = sorted({
        str(path) for pr in merged_prs for path in pr.get("changed_files", ()) if str(path)
    })
    check_rows = sorted({
        (str(name), str(state)) for pr in merged_prs for name, state in pr.get("checks", ())
    })
    refs = [f"issue:{issue_number}:closed"]
    for pr in merged_prs:
        refs.append(f"pr:{int(pr['number'])}@{str(pr.get('merge_commit_sha') or '')}")

    return {
        "terminal_state": ("CLOSED_WITH_MERGED_PR" if merged_prs else "CLOSED_WITHOUT_MERGED_PR"),
        "terminal_at": str(issue.get("closed_at") or ""),
        "evidence_refs": refs,
        "details": {
            "merged_prs": [
                {
                    "number": int(pr["number"]),
                    "merge_commit_sha": str(pr.get("merge_commit_sha") or ""),
                    "head_sha": str(pr.get("head_sha") or ""),
                }
                for pr in merged_prs
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


def _load_binding(path: Path, *, require_activation: bool = True) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "nexus.hybrid_replication.live_binding.v1":
        raise ValueError("live_binding_schema_mismatch")
    if require_activation and payload.get("activation_state") != "AUTOMATIC_CAPTURE_READY":
        raise ValueError("live_binding_not_activated")
    return payload


def build_identity_preflight_receipt(
    *,
    d0_sha256: str,
    codex_cli: str,
    previous_codex_cli: str,
    codex_executable_sha256: str,
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
    activation_allowed = (
        d0_sha256 == D0_IMPLEMENTATION_SHA256
        and len(codex_executable_sha256) == 64
        and jev_status == "VALID"
        and not provider_drift
    )
    receipt = {
        "schema": "nexus.hybrid_replication.identity_preflight.v1",
        "created_at_utc": created_at_utc,
        "d0_implementation_sha256": d0_sha256,
        "codex_cli": codex_cli,
        "previous_codex_cli": previous_codex_cli,
        "codex_executable_sha256": codex_executable_sha256,
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
    ordered = sorted(
        ((str(k), float(v)) for k, v in probs.items()),
        key=lambda item: (-item[1], item[0]),
    )
    choice = str(ans.get("choice") or "")
    valid = (
        out.get("model") == binding["jev"]["resolved_model"]
        and ans.get("type") == "choice"
        and choice in criteria
        and set(probs) == set(criteria)
        and ordered
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


def _c_prompt(snapshot: TaskSnapshot) -> tuple[str, dict[str, Any]]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "recommended_files": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string"},
            },
            "risk_notes": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string"},
            },
        },
        "required": ["summary", "recommended_files", "risk_notes"],
    }
    prompt = (
        "You are the frozen strong-Online arm for a prospective Nexus engineering "
        "replication. Work only from this pre-outcome task contract and the exact source "
        "revision mounted read-only. Do not modify files. Do not use future PR, changed-file, "
        "verifier, merge, or final-worker outcome information. Return a bounded pre-outcome "
        "implementation prediction: concise approach, likely files, and risks.\n\n"
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
                strong, strong_wall = _run_codex(
                    repo=repo,
                    revision=snapshot.pre_implementation_revision,
                    prompt=prompt,
                    schema=schema,
                    binding=binding,
                )
                fallbacks = ("DM1_TO_STRONG_ONLINE",)
            jev_usage = jev_raw.get("usage") or {}
            strong_usage = (strong or {}).get("usage") or {}
            raw_response = {
                "candidate_packet": packet,
                "jev_raw_response": jev_raw,
                "dm1_decision": decision,
                "strong_online_raw_response": strong,
                "accepted_by_frozen_policy": accepted,
            }
            raw = RawRouteResult.create(
                route="B",
                provider="typesafe" if accepted else "typesafe+openai",
                requested_model=(
                    str(binding["jev"]["requested_model"])
                    if accepted
                    else f"{binding['jev']['requested_model']}+{binding['strong_online']['requested_model']}"
                ),
                resolved_model=(
                    str(binding["jev"]["resolved_model"])
                    if accepted
                    else f"{binding['jev']['resolved_model']}+{binding['strong_online']['requested_model']}"
                ),
                model_call_count=1 if accepted else 2,
                input_tokens=int(jev_usage.get("input_tokens", 0) or 0)
                + int(strong_usage.get("input_tokens", 0) or 0),
                uncached_input_tokens=int(jev_usage.get("input_tokens", 0) or 0)
                + max(
                    0,
                    int(strong_usage.get("input_tokens", 0) or 0)
                    - int(strong_usage.get("cached_input_tokens", 0) or 0),
                ),
                output_tokens=int(jev_usage.get("output_tokens", 0) or 0)
                + int(strong_usage.get("output_tokens", 0) or 0),
                wall_time_seconds=jev_wall + strong_wall,
                failures=()
                if jev_raw.get("status") == "VALID"
                else (str(jev_raw.get("status") or "JEV_FAILURE"),),
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
    strong, wall = _run_codex(
        repo=repo,
        revision=snapshot.pre_implementation_revision,
        prompt=prompt,
        schema=schema,
        binding=binding,
    )
    usage = strong.get("usage") or {}
    raw = RawRouteResult.create(
        route="C",
        provider="openai",
        requested_model=str(binding["strong_online"]["requested_model"]),
        resolved_model=str(binding["strong_online"]["requested_model"]),
        model_call_count=1,
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        uncached_input_tokens=max(
            0,
            int(usage.get("input_tokens", 0) or 0) - int(usage.get("cached_input_tokens", 0) or 0),
        ),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        wall_time_seconds=wall,
        failures=()
        if strong.get("status") == "VALID"
        else (str(strong.get("status") or "STRONG_ONLINE_FAILURE"),),
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
    cp = _run(["gh", "api", *args], timeout=60)
    if cp.returncode != 0:
        raise RuntimeError(f"gh_api_failed:{cp.returncode}:{cp.stderr.strip()}")
    return json.loads(cp.stdout)


def _resolve_ground_truth_from_state(state: Mapping[str, Any]) -> dict[str, Any] | None:
    snapshot = state.get("snapshot") or {}
    repository = str(snapshot.get("repository") or "")
    issue_number = int(snapshot.get("issue_number") or 0)
    if not repository or not issue_number:
        raise ValueError("task_state_identity_missing")
    issue = _gh_json(f"repos/{repository}/issues/{issue_number}")
    if str(issue.get("state") or "") != "closed":
        return None

    timeline = _gh_json(
        "-X",
        "GET",
        f"repos/{repository}/issues/{issue_number}/timeline",
        "-f",
        "per_page=100",
    )
    pr_numbers = sorted({
        int(source_issue["number"])
        for item in timeline
        if isinstance(item, dict) and item.get("event") == "cross-referenced"
        for source in [item.get("source") or {}]
        for source_issue in [source.get("issue") or {}]
        if "pull_request" in source_issue
        and str(source_issue.get("repository_url") or "")
        == f"https://api.github.com/repos/{repository}"
        and isinstance(source_issue.get("number"), int)
    })
    merged: list[dict[str, Any]] = []
    for number in pr_numbers:
        pr = _gh_json(f"repos/{repository}/pulls/{number}")
        if not pr.get("merged_at"):
            continue
        files = _gh_json(
            "-X",
            "GET",
            f"repos/{repository}/pulls/{number}/files",
            "-f",
            "per_page=100",
        )
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        checks = _gh_json(f"repos/{repository}/commits/{head_sha}/check-runs?per_page=100")
        merged.append({
            "number": number,
            "merge_commit_sha": str(pr.get("merge_commit_sha") or ""),
            "head_sha": head_sha,
            "changed_files": tuple(
                str(item.get("filename") or "")
                for item in files
                if isinstance(item, dict) and item.get("filename")
            ),
            "checks": tuple(
                (
                    str(item.get("name") or ""),
                    str(item.get("conclusion") or item.get("status") or ""),
                )
                for item in checks.get("check_runs", [])
                if isinstance(item, dict)
            ),
        })
    return resolve_ground_truth_payload(issue=issue, merged_prs=tuple(merged))


def _identity_preflight_main(binding_path: Path) -> int:
    binding = _load_binding(binding_path, require_activation=False)
    d0_path = Path(str(binding["d0"]["implementation_path"]))
    d0_sha = _sha256_file(d0_path)
    binary = str(binding["strong_online"]["codex_binary"])
    version = _run([binary, "--version"], timeout=15)
    if version.returncode != 0:
        raise RuntimeError("codex_version_unavailable")
    executable = Path(str(binding["strong_online"]["codex_executable_path"]))
    executable_sha = _sha256_file(executable)

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
    receipt = build_identity_preflight_receipt(
        d0_sha256=d0_sha,
        codex_cli=version.stdout.strip(),
        previous_codex_cli=str(binding["strong_online"]["previous_codex_cli"]),
        codex_executable_sha256=executable_sha,
        jev_requested_model=str(binding["jev"]["requested_model"]),
        jev_resolved_model=str(jev_raw.get("resolved_model") or ""),
        expected_jev_resolved_model=str(binding["jev"]["resolved_model"]),
        jev_status=str(jev_raw.get("status") or ""),
        jev_usage=dict(jev_raw.get("usage") or {}),
        jev_latency_ms=wall * 1000,
        created_at_utc=dt.datetime
        .now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
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
