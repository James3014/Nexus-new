from __future__ import annotations

import json
import os
import shlex
import subprocess
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
    return providers
