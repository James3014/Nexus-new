"""Hyper-Sprint candidate prompts carry CodeIntel impact context (#1736)."""

from pathlib import Path

from nexus.research.flow.codeintel_context import sprint_codeintel_block
from nexus.research.sprint_service import (
    CandidateEval,
    SprintConfig,
    _build_llm_candidate_prompt,
    run_hyper_sprint,
)
from nexus.services.codeintel import scan_codebase

GRAPH = Path(".nexus/reports/codeintel/shared_code_graph.json")


def _repo_with_dependent(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (pkg / "user.py").write_text(
        "from pkg.core import value\n\n\ndef use():\n    return value()\n", encoding="utf-8"
    )


def _write_index(tmp_path: Path) -> None:
    (tmp_path / GRAPH).parent.mkdir(parents=True, exist_ok=True)
    scan_codebase(tmp_path, index_path=tmp_path / GRAPH)


def test_block_lists_dependents_from_cached_index(tmp_path):
    _repo_with_dependent(tmp_path)
    _write_index(tmp_path)

    block, status = sprint_codeintel_block(tmp_path, target_file="pkg/core.py")

    assert status["status"] == "ok"
    assert "[CODEINTEL IMPACT]" in block
    assert "- pkg/user.py" in block
    assert "pkg/core.py\n" in block  # the target line
    assert status["chars"] == len(block)


def test_block_reports_no_index_instead_of_scanning(tmp_path):
    _repo_with_dependent(tmp_path)

    block, status = sprint_codeintel_block(tmp_path, target_file="pkg/core.py")

    assert block == ""
    assert status["status"] == "no_index"


def test_block_reports_empty_when_nothing_depends_on_target(tmp_path):
    _repo_with_dependent(tmp_path)
    _write_index(tmp_path)

    block, status = sprint_codeintel_block(tmp_path, target_file="pkg/user.py")

    assert block == ""
    assert status["status"] == "empty"


def test_prompt_includes_block_in_full_and_compact_modes(monkeypatch):
    block = "[CODEINTEL IMPACT]\nTarget: a.py\n- b.py\n"
    full = _build_llm_candidate_prompt(
        source_code="x=1", task="t", mutation_hint="h", codeintel_block=block
    )
    monkeypatch.setenv("NEXUS_GATEWAY_COMPACT_PROMPT", "1")
    compact = _build_llm_candidate_prompt(
        source_code="x=1", task="t", mutation_hint="h", codeintel_block=block
    )

    assert block in full
    assert block in compact
    assert "[CODEINTEL IMPACT]" not in _build_llm_candidate_prompt(
        source_code="x=1", task="t", mutation_hint="h"
    )


def test_llm_sprint_passes_block_to_generator_and_records_status(monkeypatch, tmp_path):
    _repo_with_dependent(tmp_path)
    _write_index(tmp_path)
    slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    slo.parent.mkdir(parents=True, exist_ok=True)
    slo.write_text(
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8"
    )
    seen = []

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            seen.append(kwargs.get("codeintel_block", ""))
            return "def value():\n    return 2\n", {
                "source": "llm",
                "model_calls": 1,
                "quota_backoffs": 0,
            }

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(
                seed=kwargs["seed"],
                score=1.0,
                candidate_code=kwargs.get("candidate_code", ""),
                source=kwargs["source"],
            )

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(
        task="fix", target_file="pkg/core.py", candidate_count=1, llm_mode=True, safe_mode=True
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert seen and "- pkg/user.py" in seen[0]
    assert res.codeintel_context["status"] == "ok"


def test_local_only_sprint_records_skip(monkeypatch, tmp_path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(
                seed=kwargs["seed"],
                score=1.0,
                candidate_code="print('ok')\n",
                source=kwargs["source"],
            )

    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    res = run_hyper_sprint(
        repo_root=tmp_path,
        config=SprintConfig(task="fix", target_file="demo.py", candidate_count=1),
    )

    assert res.codeintel_context == {"status": "skipped_local_only"}
