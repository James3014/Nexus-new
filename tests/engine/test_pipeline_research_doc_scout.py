from types import SimpleNamespace
from pathlib import Path

from nexus.engine.pipeline_research import PipelineResearchMixin


class _DummyResearch(PipelineResearchMixin):
    def __init__(self, project_root: Path):
        self.engine = SimpleNamespace(project_root=project_root)

    def _run_experimental_research(self, **kwargs):  # type: ignore[override]
        return {
            "findings": ["ok"],
            "winner": {"params": {"k": 1}, "final_metric": 0.9},
        }


def test_stage_research_writes_doc_scout_diagnostic_map(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "rfc.md").write_text("Fix websocket timeout race with evidence.", encoding="utf-8")

    mixin = _DummyResearch(tmp_path)
    state = SimpleNamespace(metadata={"worktree_path": str(tmp_path)})
    ctx = SimpleNamespace(
        task_id="task-1",
        task_desc="fix websocket timeout race",
        bayesian_params={},
        state=state,
    )

    assert mixin._stage_research(ctx, tracer=None) is True
    diag = ctx.state.metadata["diagnostic_map"]
    assert "doc_scout" in diag
    assert diag["doc_scout"]["hits_count"] >= 1
