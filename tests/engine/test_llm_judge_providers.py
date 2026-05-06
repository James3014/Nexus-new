from __future__ import annotations

import json
import sys

from nexus.engine.autoreason_service import AutoreasonCandidate
from nexus.engine.llm_judge_providers import CommandJudgeProvider, DeterministicFakeJudgeProvider, build_judge_providers_from_env


def test_fake_judge_provider_is_opt_in():
    assert build_judge_providers_from_env({}) == []

    providers = build_judge_providers_from_env({"NEXUS_LLM_JUDGE_PROVIDERS": "fake"})

    assert len(providers) == 1
    assert isinstance(providers[0], DeterministicFakeJudgeProvider)


def test_command_judge_provider_round_trips_json(tmp_path):
    script = tmp_path / "judge.py"
    script.write_text(
        "import json, sys\n"
        "payload = json.loads(sys.stdin.read())\n"
        "ids = [item['candidate_id'] for item in payload['candidates']]\n"
        "print(json.dumps({'judge': payload['provider'], 'ranking': list(reversed(ids)), 'reason': 'ok'}))\n",
        encoding="utf-8",
    )
    provider = CommandJudgeProvider(name="gemini", command=[sys.executable, str(script)], timeout_sec=5)

    out = provider.rank(
        task_desc="fix race",
        candidates=[
            AutoreasonCandidate(candidate_id="A", summary="old", evidence_refs=[]),
            AutoreasonCandidate(candidate_id="B", summary="new", evidence_refs=["pytest passed"]),
        ],
    )

    assert out["judge"] == "gemini"
    assert out["ranking"] == ["B", "A"]


def test_command_provider_requires_explicit_command():
    providers = build_judge_providers_from_env({"NEXUS_LLM_JUDGE_PROVIDERS": "gemini,codex"})

    assert providers == []


def test_command_judge_provider_fails_closed_on_bad_json(tmp_path):
    script = tmp_path / "bad_judge.py"
    script.write_text("print('not-json')\n", encoding="utf-8")
    provider = CommandJudgeProvider(name="codex", command=[sys.executable, str(script)], timeout_sec=5)

    try:
        provider.rank(task_desc="fix race", candidates=[])
    except RuntimeError as exc:
        assert "invalid json" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("provider should fail closed")
