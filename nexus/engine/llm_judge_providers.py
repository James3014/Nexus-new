from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from nexus.engine.autoreason_service import AutoreasonCandidate, JudgeProvider


@dataclass(frozen=True)
class DeterministicFakeJudgeProvider:
    """Test-only semantic provider for wiring checks; never used by default."""

    name: str = "fake_semantic"

    def rank(self, *, task_desc: str, candidates: list[AutoreasonCandidate]) -> dict[str, Any]:
        ranked = sorted(
            candidates,
            key=lambda item: (
                "passed" in " ".join(item.evidence_refs).lower(),
                task_desc.lower() in item.summary.lower(),
                item.score,
                item.candidate_id,
            ),
            reverse=True,
        )
        return {
            "judge": self.name,
            "ranking": [item.candidate_id for item in ranked],
            "reason": "fake_semantic_rank_for_tests",
            "rubric": {item.candidate_id: {"semantic_fit": 1.0 if index == 0 else 0.5} for index, item in enumerate(ranked)},
        }


@dataclass(frozen=True)
class CommandJudgeProvider:
    """Opt-in local command adapter for Gemini/Codex style judge processes.

    The command receives one JSON payload on stdin and must write a JSON object
    containing at least `ranking` to stdout. Network/API concerns stay outside
    Nexus, so unavailable providers fail closed through AutoreasonService.
    """

    name: str
    command: Sequence[str]
    timeout_sec: float = 30.0

    def rank(self, *, task_desc: str, candidates: list[AutoreasonCandidate]) -> dict[str, Any]:
        if not self.command:
            raise RuntimeError(f"{self.name} judge command missing")
        payload = {
            "schema": "nexus_llm_judge_request_v1",
            "provider": self.name,
            "task_desc": task_desc,
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "summary": item.summary,
                    "evidence_refs": item.evidence_refs,
                    "score": item.score,
                }
                for item in candidates
            ],
        }
        proc = subprocess.run(
            list(self.command),
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=max(1.0, float(self.timeout_sec or 30.0)),
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{self.name} judge exited {proc.returncode}: {proc.stderr.strip()}")
        try:
            out = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{self.name} judge returned invalid json") from exc
        if not isinstance(out, dict):
            raise RuntimeError(f"{self.name} judge returned non-object json")
        return out


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
# Workforce local_first role the judge runs under; ranking candidates is a bounded
# classification task and qwen3.5:9b (local_qwen35_9b) is the policy's worker for it.
OLLAMA_JUDGE_ROLE = "classification"
OLLAMA_JUDGE_SYSTEM_PROMPT = (
    "You are a strict code-review judge. Rank ALL candidate fixes for the task from best to worst. "
    "Prefer candidates whose evidence shows tests passing and that fix the root cause; penalise "
    "candidates that delete or weaken tests or leave tests failing. Reply with JSON only, of the form "
    '{"ranking": [...], "reason": "..."}. The ranking array must contain every candidate id exactly once.'
)


class JudgeProviderUnavailable(RuntimeError):
    """The judge provider cannot run (policy, endpoint or model missing); fail closed."""


def resolve_ollama_judge_worker(role: str = OLLAMA_JUDGE_ROLE) -> dict[str, str]:
    """Admitted local worker for the judge role from the Workforce policy (no hard-coded model)."""
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    snapshot = WorkforcePolicyLoader().load()
    local_first = snapshot.routing.get("local_first", {}) if isinstance(snapshot.routing, Mapping) else {}
    worker_id = str(local_first.get(role) or "") if isinstance(local_first, Mapping) else ""
    worker = snapshot.workers.get(worker_id) if worker_id else None
    if worker is None:
        raise JudgeProviderUnavailable(f"no_local_worker_routed_for_role:{role}")
    if str(worker.provider) != "ollama":
        raise JudgeProviderUnavailable(f"local_worker_not_ollama:{worker_id}:{worker.provider}")
    if str(worker.availability) != "AVAILABLE":
        raise JudgeProviderUnavailable(f"local_worker_unavailable:{worker_id}:{worker.availability}")
    if role not in tuple(worker.roles or ()):
        raise JudgeProviderUnavailable(f"local_worker_lacks_role:{worker_id}:{role}")
    return {"worker_id": worker_id, "model": str(worker.model), "role": role, "state": str(worker.state)}


@dataclass(frozen=True)
class OllamaJudgeProvider:
    """Local judge over the Ollama chat API (M5 via the 127.0.0.1:11434 tunnel).

    The model is the Workforce policy's local worker for ``OLLAMA_JUDGE_ROLE``. The response
    must rank only known candidate ids; ids the model omits are appended after its ranking and
    reported in ``omitted_by_model`` (the winner is always the model's own first choice).
    """

    model: str
    worker_id: str
    base_url: str = DEFAULT_OLLAMA_URL
    timeout_sec: float = 180.0
    name: str = "ollama"

    @classmethod
    def from_policy(cls, env: Mapping[str, str] | None = None) -> "OllamaJudgeProvider":
        source = env if env is not None else os.environ
        worker = resolve_ollama_judge_worker()
        base_url = str(source.get("NEXUS_OLLAMA_URL") or DEFAULT_OLLAMA_URL).strip().rstrip("/")
        if base_url.endswith("/api/tags"):
            base_url = base_url[: -len("/api/tags")]
        return cls(model=worker["model"], worker_id=worker["worker_id"], base_url=base_url)

    def rank(self, *, task_desc: str, candidates: list[AutoreasonCandidate]) -> dict[str, Any]:
        ids = [item.candidate_id for item in candidates]
        if len(ids) < 2 or len(set(ids)) != len(ids):
            raise JudgeProviderUnavailable("judge_requires_two_distinct_candidates")
        user = json.dumps(
            {
                "task": task_desc[:2000],
                "candidate_ids": ids,
                "candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "summary": item.summary[:1500],
                        "evidence_refs": list(item.evidence_refs)[:8],
                    }
                    for item in candidates
                ],
            },
            ensure_ascii=False,
        )
        body = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [
                {"role": "system", "content": OLLAMA_JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        }
        started = time.monotonic()
        attempts: list[str] = []
        envelope: dict[str, Any] = {}
        content = ""
        parsed: Any = None
        for _attempt in range(2):
            envelope, content = self._chat(body)
            parsed = _parse_json_object(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("ranking"), list) and any(
                str(item) in set(ids) for item in parsed["ranking"]
            ):
                break
            attempts.append(hashlib.sha256(content.encode("utf-8")).hexdigest())
            parsed = None
        latency_ms = int((time.monotonic() - started) * 1000)
        if parsed is None:
            raise RuntimeError(f"ollama judge returned no usable ranking after {len(attempts)} attempts")
        model_ranking = [str(item) for item in parsed["ranking"]]
        known = [item for item in dict.fromkeys(model_ranking) if item in set(ids)]
        omitted = [item for item in ids if item not in known]
        return {
            "judge": self.name,
            "provider": "ollama",
            "model": str(envelope.get("model") or self.model),
            "worker_id": self.worker_id,
            "endpoint": self.base_url,
            "ranking": [*known, *omitted],
            "winner": known[0],
            "model_ranking": model_ranking[:16],
            "unknown_ids_dropped": [item for item in model_ranking if item not in set(ids)][:8],
            "omitted_by_model": omitted,
            "reason": str(parsed.get("reason") or "")[:500],
            "latency_ms": latency_ms,
            "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "eval_count": envelope.get("eval_count"),
            "discarded_response_sha256": attempts,
        }

    def _chat(self, body: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        if urllib.parse.urlsplit(self.base_url).scheme not in {"http", "https"}:
            raise JudgeProviderUnavailable(f"ollama_url_scheme_not_http:{self.base_url}")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:  # noqa: S310  # nosec B310 - scheme checked http(s) above
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise JudgeProviderUnavailable(f"ollama_unreachable:{self.base_url}:{exc}") from exc
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ollama endpoint returned a non-json envelope") from exc
        if not isinstance(envelope, dict):
            raise RuntimeError("ollama endpoint returned a non-object envelope")
        raw_message = envelope.get("message")
        message = raw_message if isinstance(raw_message, dict) else {}
        return envelope, str(message.get("content") or "")


def _parse_json_object(content: str) -> Any:
    """The model's JSON object; tolerate prose or code fences around one object."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None


def _provider_names(env: Mapping[str, str]) -> list[str]:
    raw = env.get("NEXUS_LLM_JUDGE_PROVIDERS", "")
    return [name.strip().lower() for name in raw.split(",") if name.strip()]


def _command_for_provider(env: Mapping[str, str], provider: str) -> list[str]:
    key = f"NEXUS_{provider.upper()}_JUDGE_CMD"
    raw = str(env.get(key, "")).strip()
    return shlex.split(raw) if raw else []


def build_judge_providers_from_env(env: Mapping[str, str] | None = None) -> list[JudgeProvider]:
    source = env or os.environ
    providers: list[JudgeProvider] = []
    for name in _provider_names(source):
        if name in {"fake", "fake_semantic", "deterministic_fake"}:
            providers.append(DeterministicFakeJudgeProvider())
            continue
        if name in {"gemini", "codex"}:
            command = _command_for_provider(source, name)
            if command:
                providers.append(CommandJudgeProvider(name=name, command=command))
            continue
        if name in {"ollama", "local", "m5"}:
            # Frozen dataclass: ``name`` is read-only, which the JudgeProvider protocol
            # (a plain attribute) does not express; same as the fake/command providers.
            providers.append(OllamaJudgeProvider.from_policy(source))  # pyright: ignore[reportArgumentType]
    return providers
