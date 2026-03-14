from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from nexus.core.action_brief import build_action_brief
from nexus.core.escalation import EscalationDecision, TaskMetadata


def test_builds_gemini_repair_brief_from_review_feedback():
    brief = build_action_brief(
        decision=EscalationDecision(
            action="gemini_repair",
            actor="gemini",
            allow_codex_patch=False,
            reason_codes=["default_gemini_repair"],
        ),
        task=TaskMetadata(language="python"),
        failure_summary="validator schema still mismatched",
        files=["scripts/core/state_contracts.py"],
        violations=[
            {
                "file": "scripts/core/state_contracts.py",
                "line": 12,
                "reason": "missing default field",
                "suggestion": "add a compatibility-safe default",
            }
        ],
    )

    assert brief.actor == "gemini"
    assert "compatibility-safe default" in brief.instructions


def test_builds_felo_brief_with_minimum_context_fields():
    brief = build_action_brief(
        decision=EscalationDecision(
            action="felo_research",
            actor="felo",
            allow_codex_patch=False,
            reason_codes=["external_signal"],
        ),
        task=TaskMetadata(
            language="python",
            has_external_dependency_signal=True,
            stacktrace_pattern="fastapi dependency override http 500",
        ),
        failure_summary="framework behavior unclear",
        files=["scripts/codex_loop_brain.py"],
        violations=[],
    )

    assert brief.actor == "felo"
    assert set(["observed", "expected", "tried", "need"]).issubset(brief.context.keys())
    assert "official behavior" in brief.instructions.lower()


def test_builds_codex_patch_brief_after_escalation():
    brief = build_action_brief(
        decision=EscalationDecision(
            action="codex_patch",
            actor="codex",
            allow_codex_patch=True,
            reason_codes=["codex_patch_threshold_reached"],
        ),
        task=TaskMetadata(language="python", task_scale="large"),
        failure_summary="same failing assertion after multiple retries",
        files=["scripts/codex_loop_brain.py", "scripts/core/context_hub.py"],
        violations=[],
    )

    assert brief.actor == "codex"
    assert "definitive compile-ready patch" in brief.instructions.lower()
