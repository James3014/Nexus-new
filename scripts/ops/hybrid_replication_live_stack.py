#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import gzip
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

_MUTATION_TERMS = (
    "implement",
    "modify",
    "change",
    "repair",
    "fix",
    "add ",
    "remove",
    "refactor",
    "update",
    "write",
)

_BOUNDED_RANKING_TERMS = (
    "choose the one supplied candidate",
    "choose one supplied candidate",
    "rank the supplied candidate",
    "rank supplied candidate",
    "use only supplied candidate ids",
)


def classify_shadow_stratum(*, title: str, body: str) -> str:
    text = f"{title}\n{body}".lower()
    if "[hybrid_canary:a]" in text:
        return "A"
    if "[hybrid_canary:b]" in text:
        return "B"
    if "[hybrid_canary:c]" in text:
        return "C"
    if any(term in text for term in _BOUNDED_RANKING_TERMS):
        return "B"
    if any(term in text for term in _MUTATION_TERMS):
        return "C"
    # Fail closed to semantic work. A is granted only by an actual
    # deterministic closure witness, never by a lexical guess.
    return "C"


_PATH_RE = re.compile(
    r"((?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|mjs|cjs|json|ya?ml|toml|ini|cfg|sh|md|txt)))"
)


def _sha_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _literal_task_paths(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(1).lstrip("./") for match in _PATH_RE.finditer(text)))


def build_d0_packet(
    *,
    repository_root: str | Path,
    donor_root: str | Path,
    issue_number: int,
    title: str,
    body: str,
    revision: str,
) -> dict[str, Any]:
    repo = Path(repository_root)
    donor = Path(donor_root)
    freeze_path = donor / "D0_V2_FROZEN.json"
    impl_path = donor / "d0_v2_develop.py"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    actual_impl_sha = _sha_file(impl_path)
    if actual_impl_sha != str(freeze.get("implementation_sha256") or ""):
        raise ValueError("d0_implementation_hash_mismatch")

    spec = importlib.util.spec_from_file_location("nexus_hybrid_d0_v2_frozen", impl_path)
    if spec is None or spec.loader is None:
        raise ValueError("d0_import_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPO = repo
    if hasattr(module, "FILE_CACHE"):
        module.FILE_CACHE.clear()
    if hasattr(module, "GREP_CACHE"):
        module.GREP_CACHE.clear()
    if hasattr(module, "LOG_CACHE"):
        module.LOG_CACHE.clear()
    if hasattr(module, "SHOW_NAMES_CACHE"):
        module.SHOW_NAMES_CACHE.clear()

    statement = f"{title}\n\n{body}".strip()
    ranked, _scores, why, query = module.rank_task(revision, statement, freeze["weights"])
    literal = _literal_task_paths(statement)
    ordered_paths: list[str] = []
    for path in [*literal, *ranked]:
        if path not in ordered_paths:
            ordered_paths.append(path)
        if len(ordered_paths) >= int(freeze.get("candidate_budget_k", 8)):
            break

    candidates: list[dict[str, Any]] = []
    for index, path in enumerate(ordered_paths, start=1):
        if path in literal:
            source = "LITERAL_TASK_PATH"
            evidence = ["literal_path_in_issue_body"]
        else:
            source = "D0_V2_FROZEN"
            evidence = [str(item) for item in list(why.get(path, []))[:10]]
        candidates.append(
            {
                "id": f"C{index}",
                "path": path,
                "source": source,
                "evidence": evidence,
                "packet_rank": index,
            }
        )

    packet = {
        "schema": "nexus.hybrid_economics_r3.deterministic_packet.v2",
        "shaping_rule": (
            "Preserve literal task paths as hard facts, then append frozen D0_V2 top candidates not already present."
        ),
        "retriever": "D0_V2_FROZEN",
        "freeze_sha256": _sha_file(freeze_path),
        "implementation_sha256": actual_impl_sha,
        "execution_start_base": revision,
        "issue": int(issue_number),
        "query_projection": query,
        "literal_task_paths": literal,
        "d0_v2_original_candidates": [
            {
                "rank": index,
                "path": path,
                "evidence": [str(item) for item in list(why.get(path, []))[:10]],
            }
            for index, path in enumerate(ranked, start=1)
        ],
        "candidates": candidates,
    }
    packet["source_packet_sha256"] = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    return packet


def d2_project_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(packet)
    candidates = [dict(item) for item in source.get("candidates", [])]
    literal_paths = [str(item) for item in source.get("literal_task_paths", [])]
    source_sha = str(source.get("source_packet_sha256") or "")
    if not source_sha:
        import hashlib

        source_sha = hashlib.sha256(
            json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
    return {
        "schema": "nexus.deterministic_shaping_v2.reversible_packet.v1",
        "acquisition_identity": {
            "retriever": source.get("retriever"),
            "freeze_sha256": source.get("freeze_sha256"),
            "implementation_sha256": source.get("implementation_sha256"),
        },
        "execution_start_base": source.get("execution_start_base"),
        "issue": source.get("issue"),
        "literal_task_paths": literal_paths,
        "candidates": candidates,
        "source_packet_sha256": source_sha,
        "projection_rule": (
            "Representation dedup only; exact final candidates/literal paths preserved. "
            "Omitted fields are duplicate acquisition-internal projections and do not assert absence."
        ),
    }


def build_jev_request(
    *,
    packet: Mapping[str, Any],
    task_contract_text: str,
    task_identity: str,
) -> dict[str, Any]:
    candidates = [dict(item) for item in packet.get("candidates", [])]
    criteria = {
        str(item["id"]): (
            f"Candidate file: {item['path']}. Admitted deterministic evidence: "
            + "; ".join(str(value) for value in item.get("evidence", []))
        )
        for item in candidates
    }
    criteria["ESCALATE"] = (
        "No single supplied candidate is adequately supported, or evidence is too ambiguous "
        "to choose safely."
    )
    return {
        "model": "jev-latest",
        "questions": {
            "file_choice": {
                "criteria": criteria,
                "instructions": (
                    "Choose the ONE supplied candidate file most likely to require modification "
                    "for this task. Use only supplied candidate IDs. Do not invent a path. "
                    "If no single candidate is adequately supported or evidence is too ambiguous, "
                    "choose ESCALATE."
                ),
                "type": "choice",
            }
        },
        "state": {
            "boundary": (
                "Choose only among supplied candidate IDs. Candidate evidence is advisory/incomplete; "
                "confidence cannot establish evidence sufficiency or absence."
            ),
            "candidate_catalog": candidates,
            "issue": packet.get("issue"),
            "source_revision": packet.get("execution_start_base"),
            "task_contract_text": task_contract_text,
            "task_identity": task_identity,
        },
    }


def parse_jev_response(
    response: Mapping[str, Any],
    *,
    criteria: set[str],
) -> dict[str, Any]:
    answers = response.get("answers")
    answer = answers.get("file_choice") if isinstance(answers, Mapping) else None
    answer = answer if isinstance(answer, Mapping) else {}
    raw_probs = answer.get("probabilities")
    probabilities = dict(raw_probs) if isinstance(raw_probs, Mapping) else {}
    ordered: list[tuple[str, float]] = []
    try:
        ordered = sorted(
            ((str(key), float(value)) for key, value in probabilities.items()),
            key=lambda item: (-item[1], item[0]),
        )
    except (TypeError, ValueError):
        ordered = []
    choice = str(answer.get("choice") or "")
    valid = bool(
        str(response.get("model") or "")
        and answer.get("type") == "choice"
        and choice in criteria
        and set(probabilities) == set(criteria)
        and all(0.0 <= float(value) <= 1.0 for value in probabilities.values())
        and abs(sum(float(value) for value in probabilities.values()) - 1.0) <= 0.03
        and ordered
        and choice == ordered[0][0]
        and isinstance(response.get("usage"), Mapping)
    )
    top = float(probabilities.get(choice, 0.0)) if choice in probabilities else 0.0
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    return {
        "status": "VALID" if valid else "INVALID_RESPONSE",
        "requested_model": "jev-latest",
        "resolved_model": str(response.get("model") or ""),
        "choice": choice or None,
        "confidence": answer.get("confidence"),
        "top_probability": top,
        "second_probability": second,
        "margin": top - second,
        "probabilities": probabilities,
        "usage": dict(response.get("usage") or {}) if isinstance(response.get("usage"), Mapping) else {},
    }


def execute_effect_once(
    *,
    effect_root: str | Path,
    effect_id: str,
    producer: Any,
) -> dict[str, Any]:
    root = Path(effect_root)
    effect_dir = root / effect_id
    effect_dir.mkdir(parents=True, exist_ok=True)
    started = effect_dir / "STARTED.json"
    result = effect_dir / "RESULT.json"

    if result.exists():
        payload = json.loads(result.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("stack_effect_result_malformed")
        return payload

    try:
        with started.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "schema": "nexus.hybrid_replication.stack_effect_started.v1",
                        "effect_id": effect_id,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        if result.exists():
            payload = json.loads(result.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        raise RuntimeError("stack_effect_outcome_unknown") from exc

    payload = producer()
    if not isinstance(payload, dict):
        raise ValueError("stack_effect_result_must_be_object")
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    temporary = effect_dir / f".RESULT.{os.getpid()}.tmp"
    with temporary.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, result)
    except FileExistsError:
        pass
    finally:
        temporary.unlink(missing_ok=True)
    persisted = json.loads(result.read_text(encoding="utf-8"))
    if not isinstance(persisted, dict):
        raise ValueError("stack_effect_result_malformed")
    return persisted


def parse_codex_usage(events_path: str | Path) -> dict[str, int]:
    path = Path(events_path)
    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
    }
    turns = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "turn.completed":
                continue
            turns += 1
            usage = event.get("usage") or {}
            for key in totals:
                totals[key] += int(usage.get(key, 0) or 0)
    return {
        **totals,
        "uncached_input_tokens": totals["input_tokens"] - totals["cached_input_tokens"],
        "turns": turns,
    }


def _canonical_sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def decode_capture_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    body_blob = str(payload.get("body_gzip_base64") or "")
    try:
        body = gzip.decompress(base64.b64decode(body_blob.encode("ascii"))).decode("utf-8")
    except Exception as exc:
        raise ValueError("capture_body_decode_failed") from exc
    required = {
        "repository": str(payload.get("repository") or ""),
        "issue_number": int(payload.get("issue_number") or 0),
        "title": str(payload.get("title") or ""),
        "body": body,
        "revision": str(payload.get("pre_implementation_revision") or ""),
        "capture_sha256": str(payload.get("capture_sha256") or ""),
    }
    if not required["repository"] or not required["issue_number"] or len(required["revision"]) != 40:
        raise ValueError("capture_identity_incomplete")
    if len(required["capture_sha256"]) != 64:
        raise ValueError("capture_sha256_missing")
    return required


def ensure_revision(repository_root: str | Path, revision: str) -> None:
    repo = Path(repository_root)
    check = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode == 0:
        return
    fetch = subprocess.run(
        ["git", "fetch", "--quiet", "origin", revision],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if fetch.returncode != 0:
        raise RuntimeError(f"source_revision_fetch_failed:{fetch.stderr.strip()}")
    verify = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode != 0:
        raise RuntimeError("source_revision_unavailable_after_fetch")


def _add_detached_worktree(repository_root: Path, revision: str, target: Path) -> None:
    if target.exists():
        raise RuntimeError("shadow_worktree_path_already_exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), revision],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"shadow_worktree_add_failed:{completed.stderr.strip()}")


def _remove_detached_worktree(repository_root: Path, target: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(target)],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_codex_commands(events_path: str | Path) -> list[str]:
    path = Path(events_path)
    commands: list[str] = []
    if not path.exists():
        return commands
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
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
                    elif isinstance(value, (Mapping, list)):
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)
    return commands


_FORBIDDEN_SHADOW_COMMANDS = (
    re.compile(r"\bgit\s+(push|commit|fetch|pull|clone)\b", re.I),
    re.compile(r"\bgh\s+", re.I),
    re.compile(r"\bcurl\s+", re.I),
    re.compile(r"\bwget\s+", re.I),
    re.compile(r"\bssh\s+", re.I),
    re.compile(r"\bpip\s+install\b", re.I),
    re.compile(r"\buv\s+pip\s+install\b", re.I),
    re.compile(r"\bnpm\s+install\b", re.I),
)


def _codex_identity(codex: str) -> dict[str, Any]:
    resolved = shutil.which(codex) if os.path.sep not in codex else codex
    if not resolved:
        raise RuntimeError("codex_executable_unavailable")
    version = subprocess.check_output([resolved, "--version"], text=True).strip()
    path = Path(resolved)
    executable_sha = _sha_file(path) if path.is_file() else None
    return {
        "path": str(path),
        "version": version,
        "sha256": executable_sha,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_codex(
    *,
    codex: str,
    model: str,
    repository_root: Path,
    revision: str,
    workspace_root: Path,
    run_root: Path,
    prompt: str,
    output_schema: Mapping[str, Any],
    sandbox: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    ensure_revision(repository_root, revision)
    _add_detached_worktree(repository_root, revision, workspace_root)
    try:
        run_root.mkdir(parents=True, exist_ok=True)
        schema_path = run_root / "OUTPUT_SCHEMA.json"
        events_path = run_root / "codex.jsonl"
        last_path = run_root / "last.json"
        _write_json(schema_path, output_schema)
        identity = _codex_identity(codex)
        command = [
            identity["path"],
            "--no-daemon",
            "exec",
            "-m",
            model,
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "-s",
            sandbox,
            "-C",
            str(workspace_root),
            "--output-schema",
            str(schema_path),
            "-o",
            str(last_path),
            prompt,
        ]
        started = time.perf_counter()
        timed_out = False
        with events_path.open("w", encoding="utf-8") as handle:
            try:
                completed = subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                returncode = 124
                timed_out = True
        wall = time.perf_counter() - started
        try:
            final_response = json.loads(last_path.read_text(encoding="utf-8"))
            parse_error = None
        except Exception as exc:
            final_response = {}
            parse_error = f"{type(exc).__name__}:{exc}"
        usage = parse_codex_usage(events_path)
        commands = parse_codex_commands(events_path)
        forbidden = [
            command_text
            for command_text in commands
            if any(pattern.search(command_text) for pattern in _FORBIDDEN_SHADOW_COMMANDS)
        ]
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"],
            cwd=workspace_root,
            capture_output=True,
            text=False,
            check=False,
        ).stdout
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"], cwd=workspace_root, text=True
        ).splitlines()
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=workspace_root,
            text=True,
        ).splitlines()
        untracked_hashes = {}
        for rel in untracked:
            path = workspace_root / rel
            if path.is_file():
                untracked_hashes[rel] = _sha_file(path)
        return {
            "returncode": returncode,
            "timed_out": timed_out,
            "wall_time_seconds": wall,
            "usage": usage,
            "final_response": final_response,
            "parse_error": parse_error,
            "commands": commands,
            "forbidden_commands": forbidden,
            "changed_files": sorted(set(changed + untracked)),
            "diff_sha256": hashlib.sha256(diff).hexdigest(),
            "untracked_sha256": untracked_hashes,
            "events_sha256": _sha_file(events_path),
            "codex_identity": identity,
        }
    finally:
        _remove_detached_worktree(repository_root, workspace_root)


def call_jev_provider(
    *,
    request_payload: Mapping[str, Any],
    endpoint: str,
    keychain_account: str,
    keychain_service: str,
) -> dict[str, Any]:
    key = subprocess.check_output(
        [
            "security",
            "find-generic-password",
            "-a",
            keychain_account,
            "-s",
            keychain_service,
            "-w",
        ],
        text=True,
    ).strip()
    if not key:
        raise RuntimeError("jev_keychain_secret_empty")
    request_bytes = json.dumps(
        request_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    criteria = set(request_payload["questions"]["file_choice"]["criteria"])
    attempts: list[dict[str, Any]] = []
    response_payload: dict[str, Any] | None = None
    total_started = time.perf_counter()
    for attempt in range(1, 3):
        http_request = urllib.request.Request(
            endpoint,
            data=request_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
            },
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(http_request, timeout=45) as response:
                response_payload = json.loads(response.read())
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "SUCCESS",
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            break
        except urllib.error.HTTPError as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": f"HTTP_{exc.code}",
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "detail": exc.read().decode("utf-8", "replace")[:300],
                }
            )
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": (
                        "TIMEOUT"
                        if "timeout" in type(exc).__name__.lower()
                        else "NETWORK_FAILURE"
                    ),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "detail": str(exc)[:300],
                }
            )
    wall = time.perf_counter() - total_started
    if response_payload is None:
        return {
            "status": "PROVIDER_FAILURE",
            "requested_model": "jev-latest",
            "resolved_model": "",
            "choice": None,
            "top_probability": 0.0,
            "margin": 0.0,
            "probabilities": {},
            "usage": {},
            "attempts": attempts,
            "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "wall_time_seconds": wall,
        }
    parsed = parse_jev_response(response_payload, criteria=criteria)
    parsed["attempts"] = attempts
    parsed["request_sha256"] = hashlib.sha256(request_bytes).hexdigest()
    parsed["response_sha256"] = _canonical_sha(response_payload)
    parsed["wall_time_seconds"] = wall
    return parsed


def _codex_ranking_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ranked_files": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 8,
                "uniqueItems": True,
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "reasoning_summary": {"type": "string"},
        },
        "required": ["ranked_files", "confidence", "reasoning_summary"],
        "additionalProperties": False,
    }


def _codex_coding_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "verification_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["summary", "verification_notes"],
        "additionalProperties": False,
    }


def run_codex_ranking(
    *,
    repository_root: Path,
    revision: str,
    packet: Mapping[str, Any],
    task_contract_text: str,
    run_root: Path,
    codex: str,
    model: str,
) -> dict[str, Any]:
    candidates = [dict(item) for item in packet.get("candidates", [])]
    prompt = (
        "You are the strong-Online fallback for a frozen finite-candidate ranking experiment.\n"
        "Use only the supplied candidate paths. You may inspect the exact frozen checkout read-only. "
        "Do not modify files and do not use network or remote Git operations. "
        "Return JSON matching the schema.\n\nTASK CONTRACT:\n"
        + task_contract_text
        + "\n\nCANDIDATES:\n"
        + json.dumps(candidates, ensure_ascii=False, indent=2)
    )
    outcome = _run_codex(
        codex=codex,
        model=model,
        repository_root=repository_root,
        revision=revision,
        workspace_root=run_root / "workspace",
        run_root=run_root,
        prompt=prompt,
        output_schema=_codex_ranking_schema(),
        sandbox="read-only",
    )
    allowed = {str(item.get("path")) for item in candidates}
    ranked = outcome["final_response"].get("ranked_files")
    valid = bool(
        outcome["returncode"] == 0
        and not outcome["forbidden_commands"]
        and isinstance(ranked, list)
        and 1 <= len(ranked) <= 8
        and len(ranked) == len(set(ranked))
        and all(isinstance(item, str) and item in allowed for item in ranked)
    )
    outcome["protocol_valid"] = valid
    return outcome


def run_codex_coding(
    *,
    repository_root: Path,
    revision: str,
    title: str,
    body: str,
    run_root: Path,
    codex: str,
    model: str,
) -> dict[str, Any]:
    prompt = (
        "You are a research-only shadow implementer. Work only inside the supplied ephemeral "
        "checkout. Implement the bounded task as if preparing a candidate, but DO NOT commit, push, "
        "open or modify GitHub objects, install dependencies, or use network commands. "
        "Do not touch any external runtime. Return JSON matching the output schema.\n\n"
        f"TITLE: {title}\n\nTASK CONTRACT:\n{body}"
    )
    outcome = _run_codex(
        codex=codex,
        model=model,
        repository_root=repository_root,
        revision=revision,
        workspace_root=run_root / "workspace",
        run_root=run_root,
        prompt=prompt,
        output_schema=_codex_coding_schema(),
        sandbox="workspace-write",
    )
    outcome["protocol_valid"] = bool(
        outcome["returncode"] == 0
        and not outcome["forbidden_commands"]
        and isinstance(outcome["final_response"], Mapping)
    )
    return outcome


def _raw_result(
    *,
    route: str,
    provider: str,
    requested_model: str,
    resolved_model: str,
    model_call_count: int,
    input_tokens: int | None,
    uncached_input_tokens: int | None,
    output_tokens: int | None,
    wall_time_seconds: float,
    failures: list[str],
    retries: int,
    fallbacks: list[str],
    raw_response: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "route": route,
        "provider": provider,
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "model_call_count": model_call_count,
        "input_tokens": input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "output_tokens": output_tokens,
        "wall_time_seconds": wall_time_seconds,
        "failures": failures,
        "retries": retries,
        "fallbacks": fallbacks,
        "raw_response": dict(raw_response),
        "output_sha256": _canonical_sha(raw_response),
    }


def _deterministic_canary_outcome(
    *,
    repository_root: Path,
    revision: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    paths = _literal_task_paths(f"{title}\n{body}")
    if not paths:
        raise ValueError("a_canary_requires_literal_path")
    results = {}
    for path in paths:
        check = subprocess.run(
            ["git", "cat-file", "-e", f"{revision}:{path}"],
            cwd=repository_root,
            capture_output=True,
            check=False,
        )
        results[path] = check.returncode == 0
    receipt = {
        "schema": "nexus.hybrid_replication.deterministic_canary.v1",
        "revision": revision,
        "path_exists": results,
        "status": "PASS" if all(results.values()) else "FAIL",
    }
    return {
        "stratum": "A",
        "deterministic_receipt": receipt,
        "candidate_packet": None,
        "jev_raw_response": None,
        "dm1_decision": None,
        "strong_online_raw_response": None,
        "raw_result": _raw_result(
            route="A",
            provider="deterministic",
            requested_model="",
            resolved_model="",
            model_call_count=0,
            input_tokens=0,
            uncached_input_tokens=0,
            output_tokens=0,
            wall_time_seconds=0.0,
            failures=[] if receipt["status"] == "PASS" else ["DETERMINISTIC_CANARY_FAIL"],
            retries=0,
            fallbacks=[],
            raw_response=receipt,
        ),
    }


def produce_stack_outcome(
    *,
    capture_payload: Mapping[str, Any],
    repository_map: Mapping[str, str],
    d0_root: Path,
    effect_root: Path,
    codex: str,
    online_model: str,
    jev_endpoint: str,
    keychain_account: str,
    keychain_service: str,
) -> dict[str, Any]:
    capture = decode_capture_payload(capture_payload)
    repo_name = capture["repository"]
    if repo_name not in repository_map:
        raise ValueError("repository_not_bound")
    repo = Path(repository_map[repo_name])
    ensure_revision(repo, capture["revision"])
    title = capture["title"]
    body = capture["body"]
    stratum = classify_shadow_stratum(title=title, body=body)
    task_identity = f"{repo_name}#{capture['issue_number']}"
    run_root = effect_root / capture["capture_sha256"]

    if stratum == "A":
        return _deterministic_canary_outcome(
            repository_root=repo,
            revision=capture["revision"],
            title=title,
            body=body,
        )

    if stratum == "B":
        d0_packet = build_d0_packet(
            repository_root=repo,
            donor_root=d0_root,
            issue_number=capture["issue_number"],
            title=title,
            body=body,
            revision=capture["revision"],
        )
        packet = d2_project_packet(d0_packet)
        request_payload = build_jev_request(
            packet=packet,
            task_contract_text=f"{title}\n\n{body}",
            task_identity=task_identity,
        )
        jev = call_jev_provider(
            request_payload=request_payload,
            endpoint=jev_endpoint,
            keychain_account=keychain_account,
            keychain_service=keychain_service,
        )
        accepted = bool(
            jev["status"] == "VALID"
            and jev.get("choice") != "ESCALATE"
            and float(jev.get("top_probability") or 0.0) >= 0.70
            and float(jev.get("margin") or 0.0) >= 0.30
        )
        dm1 = {
            "choice": jev.get("choice"),
            "top_probability": jev.get("top_probability"),
            "margin": jev.get("margin"),
            "accepted": accepted,
            "selected_path": next(
                (
                    item.get("path")
                    for item in packet["candidates"]
                    if item.get("id") == jev.get("choice")
                ),
                None,
            ),
        }
        jev_usage = jev.get("usage") or {}
        if accepted:
            raw_response = {
                "d0_packet_sha256": _canonical_sha(d0_packet),
                "d2_packet_sha256": _canonical_sha(packet),
                "jev": jev,
                "dm1": dm1,
            }
            return {
                "stratum": "B",
                "deterministic_receipt": {
                    "retriever": "D0_V2_FROZEN",
                    "freeze_sha256": d0_packet["freeze_sha256"],
                    "implementation_sha256": d0_packet["implementation_sha256"],
                },
                "candidate_packet": packet,
                "jev_raw_response": jev,
                "dm1_decision": dm1,
                "strong_online_raw_response": None,
                "raw_result": _raw_result(
                    route="B",
                    provider="typesafe-systemone",
                    requested_model="jev-latest",
                    resolved_model=str(jev.get("resolved_model") or ""),
                    model_call_count=1,
                    input_tokens=int(jev_usage.get("input_tokens", 0) or 0),
                    uncached_input_tokens=int(jev_usage.get("input_tokens", 0) or 0),
                    output_tokens=int(jev_usage.get("output_tokens", 0) or 0),
                    wall_time_seconds=float(jev.get("wall_time_seconds", 0.0) or 0.0),
                    failures=[],
                    retries=max(0, len(jev.get("attempts") or []) - 1),
                    fallbacks=[],
                    raw_response=raw_response,
                ),
            }

        fallback = run_codex_ranking(
            repository_root=repo,
            revision=capture["revision"],
            packet=packet,
            task_contract_text=f"{title}\n\n{body}",
            run_root=run_root / "strong-online-fallback",
            codex=codex,
            model=online_model,
        )
        fallback_usage = fallback["usage"]
        raw_response = {
            "d0_packet_sha256": _canonical_sha(d0_packet),
            "d2_packet_sha256": _canonical_sha(packet),
            "jev": jev,
            "dm1": dm1,
            "strong_online_fallback": fallback,
        }
        failures = []
        if jev["status"] != "VALID":
            failures.append(str(jev["status"]))
        if not fallback["protocol_valid"]:
            failures.append("STRONG_ONLINE_FALLBACK_PROTOCOL_INVALID")
        return {
            "stratum": "B",
            "deterministic_receipt": {
                "retriever": "D0_V2_FROZEN",
                "freeze_sha256": d0_packet["freeze_sha256"],
                "implementation_sha256": d0_packet["implementation_sha256"],
            },
            "candidate_packet": packet,
            "jev_raw_response": jev,
            "dm1_decision": dm1,
            "strong_online_raw_response": fallback,
            "raw_result": _raw_result(
                route="B",
                provider="typesafe-systemone+codex-cli",
                requested_model=f"jev-latest+{online_model}",
                resolved_model=f"{jev.get('resolved_model') or 'UNRESOLVED'}+UNOBSERVED_BY_CODEX_CLI",
                model_call_count=2,
                input_tokens=int(jev_usage.get("input_tokens", 0) or 0)
                + int(fallback_usage.get("input_tokens", 0) or 0),
                uncached_input_tokens=int(jev_usage.get("input_tokens", 0) or 0)
                + int(fallback_usage.get("uncached_input_tokens", 0) or 0),
                output_tokens=int(jev_usage.get("output_tokens", 0) or 0)
                + int(fallback_usage.get("output_tokens", 0) or 0),
                wall_time_seconds=float(jev.get("wall_time_seconds", 0.0) or 0.0)
                + float(fallback.get("wall_time_seconds", 0.0) or 0.0),
                failures=failures,
                retries=max(0, len(jev.get("attempts") or []) - 1),
                fallbacks=["STRONG_ONLINE"],
                raw_response=raw_response,
            ),
        }

    strong = run_codex_coding(
        repository_root=repo,
        revision=capture["revision"],
        title=title,
        body=body,
        run_root=run_root / "strong-online",
        codex=codex,
        model=online_model,
    )
    usage = strong["usage"]
    failures = [] if strong["protocol_valid"] else ["STRONG_ONLINE_PROTOCOL_INVALID"]
    raw_response = {
        "shadow_execution": strong,
        "requested_model": online_model,
        "resolved_model_observed": False,
    }
    return {
        "stratum": "C",
        "deterministic_receipt": {
            "status": "INSUFFICIENT_FOR_DETERMINISTIC_OR_TYPED_FINITE_CLOSE"
        },
        "candidate_packet": None,
        "jev_raw_response": None,
        "dm1_decision": None,
        "strong_online_raw_response": strong,
        "raw_result": _raw_result(
            route="C",
            provider="codex-cli",
            requested_model=online_model,
            resolved_model="UNOBSERVED_BY_CODEX_CLI",
            model_call_count=1,
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            uncached_input_tokens=int(usage.get("uncached_input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            wall_time_seconds=float(strong.get("wall_time_seconds", 0.0) or 0.0),
            failures=failures,
            retries=0,
            fallbacks=[],
            raw_response=raw_response,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-map", required=True)
    parser.add_argument("--d0-root", required=True)
    parser.add_argument("--effect-root", required=True)
    parser.add_argument("--codex", default="/opt/homebrew/bin/codex")
    parser.add_argument("--online-model", default="gpt-5.6-luna")
    parser.add_argument("--jev-endpoint", default="https://api.typesafe.ai/v1/systemone")
    parser.add_argument("--jev-keychain-account", default=getpass.getuser())
    parser.add_argument("--jev-keychain-service", default="typesafe-api-key")
    args = parser.parse_args()

    payload = json.load(__import__("sys").stdin)
    repository_map = json.loads(Path(args.repo_map).read_text(encoding="utf-8"))
    if not isinstance(repository_map, dict):
        raise SystemExit("repo map must be a JSON object")

    capture = decode_capture_payload(payload)

    def producer() -> dict[str, Any]:
        return produce_stack_outcome(
            capture_payload=payload,
            repository_map={str(k): str(v) for k, v in repository_map.items()},
            d0_root=Path(args.d0_root),
            effect_root=Path(args.effect_root),
            codex=args.codex,
            online_model=args.online_model,
            jev_endpoint=args.jev_endpoint,
            keychain_account=args.jev_keychain_account,
            keychain_service=args.jev_keychain_service,
        )

    outcome = execute_effect_once(
        effect_root=Path(args.effect_root),
        effect_id=capture["capture_sha256"],
        producer=producer,
    )
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
