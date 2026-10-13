from pathlib import Path
import json
from unittest.mock import patch

from nexus.engine.pipeline import NexusPipeline


class _DummyPolicyManager:
    def apply_policy_to_state(self, state, task_desc):
        return None


class _DummyStateIO:
    def __init__(self):
        self._state = None

    def save_global_state(self, state):
        self._state = state


class _DummyCommander:
    def next_step(self, status="started", state=None):
        return None


class _DummyHub:
    def make_pre_routing_decision(self, task_id, payload):
        return {}

    def assemble_diag_pack(self, files, task_desc):
        return {"task": task_desc, "files": files}

    def assemble_feature_pack(self, plan=None):
        return {"plan": plan or {}}


class _DummyAccumulator:
    def record(self, state, phase, payload, overhead=0):
        return None


class _DummyHealthEvaluator:
    def evaluate(self, state, success):
        return 95.0 if success else 60.0


class _DummyResearchPolicy:
    def route(self, decision, task_desc, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(
            should_research=False, mode="skip", reason="dummy", rounds=0, stable_wins=0
        )


class _DummyPlanner:
    def __init__(self):
        self.name = "P"
        self.priority = 10
    
    def should_run(self, ctx):
        return True

    def execute(self, pipeline, ctx):
        res = self.run(ctx.state, ctx.kwargs)
        from nexus.engine.phase_plugin import PhaseResult
        return PhaseResult(status="success", mutations=res, events=[])

    def run(self, state, context):
        return {"intent_pass": True, "risk_score": 0.1, "tokens_used": 1}


class _DummyResearch:
    def __init__(self):
        self.name = "X"
        self.priority = 20

    def should_run(self, ctx):
        return True

    def execute(self, pipeline, ctx):
        res = self.run(ctx.state, ctx.kwargs)
        from nexus.engine.phase_plugin import PhaseResult
        # Convert SUCCESS to success for Literal match
        status = res.get("status", "success").lower()
        return PhaseResult(status=status, mutations=res, events=[])

    def run(self, state, context):
        return {"status": "SUCCESS", "findings": [], "tokens_used": 0}


class _DummyDiagnose:
    """D is required before R by the fail-closed runtime phase contract (S->P->D->R)."""

    def __init__(self):
        self.name = "D"
        self.priority = 25

    def should_run(self, ctx):
        return True

    def execute(self, pipeline, ctx):
        from nexus.engine.phase_plugin import PhaseResult
        return PhaseResult(status="success", mutations={"tokens_used": 0}, events=[])


class _DummyAudit:
    """The composed A executor is a required fail-closed audit gate; it must approve explicitly."""

    def __init__(self):
        self.name = "A"
        self.priority = 40

    def should_run(self, ctx):
        return True

    def execute(self, pipeline, ctx):
        from nexus.engine.phase_plugin import PhaseResult
        return PhaseResult(status="success", mutations={"status": "APPROVED"}, events=[])


class _DummyRepair:
    def __init__(self):
        self.name = "R"
        self.priority = 30

    def should_run(self, ctx):
        return True

    def execute(self, pipeline, ctx):
        res = self.run(ctx.state, ctx.kwargs)
        from nexus.engine.phase_plugin import PhaseResult
        return PhaseResult(status="success", mutations=res, events=[])

    def run(self, state, pack):
        return {
            "status": "APPROVED",
            "result_object": {
                "status": "APPROVED",
                "patch_generated": True,
                "patch_apply_success": True,
                "no_change_reason": "",
                "proof_type": "git_diff_checksum",
                "proof_value": "abc123",
            },
            "tokens_used": 1,
        }


class _DummyReviewStatusNormalizer:
    @staticmethod
    def normalize(raw):
        return ("APPROVED", str(raw).upper() == "APPROVED")


class _DummyEngine:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.run_dir = project_root / ".nexus" / "run"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.policy_manager = _DummyPolicyManager()
        self.state_io = _DummyStateIO()
        self.commander = _DummyCommander()
        self.hub = _DummyHub()
        self.accumulator = _DummyAccumulator()
        self.health_evaluator = _DummyHealthEvaluator()
        self.research_policy = _DummyResearchPolicy()
        self.phases = {
            "P": _DummyPlanner(),
            "X": _DummyResearch(),
            "D": _DummyDiagnose(),
            "R": _DummyRepair(),
            "A": _DummyAudit(),
        }
        self.max_retries = 3
        self.ReviewStatusNormalizer = _DummyReviewStatusNormalizer

    def _add_step_to_history(self, state, phase, status="completed", metadata=None, summary=None):
        from nexus.core.state_contracts import StepRecord
        from datetime import datetime
        state.steps_history.append(
            StepRecord(
                phase=phase,
                step_id=f"{phase}-1",
                status=status,
                started_at=datetime.now(),
                ended_at=datetime.now(),
                metadata=metadata or {},
                summary=summary,
            )
        )


def test_pipeline_writes_skill_outcome_events(tmp_path: Path):
    engine = _DummyEngine(tmp_path)
    # Core phases come only from composed phase executors (engine.phases is not consulted for
    # P/X/D once any executor is registered), so hand the dummies in through that seam.
    # C must be the real crystallize executor: success is withheld without its verified record.
    from nexus.engine.phase_executors import build_crystallize_executor

    executors = {**engine.phases, "C": build_crystallize_executor(tmp_path, engine.run_dir)}
    with patch.object(NexusPipeline, "_build_default_phase_executors", return_value=executors):
        pipeline = NexusPipeline(engine)
    ok = pipeline.run("pipeline outcome event test", "bug")
    assert ok is True

    event_path = tmp_path / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
    assert event_path.exists()
    rows = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert all(str(row.get("decision_id", "")).startswith("dec_") for row in rows)


# ARCHIVED 2026-10-13 legacy-engine: this file tests (in whole or in part) modules archived with
# the legacy NexusEngine (nexus.engine.pipeline); see ARCHIVED_2026-10-13-legacy-engine.md.
# It keeps running with unchanged node ids until the deletion PR removes it with those modules.
