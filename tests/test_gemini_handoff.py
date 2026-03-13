from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.gemini_handoff import build_gemini_prompt


def test_build_prompt_includes_action_brief_and_context():
    prompt = build_gemini_prompt(
        {
            "next_action": "felo_research",
            "summary": "framework behavior unclear",
            "escalation_reasons": ["external_signal", "repeated_failure"],
            "action_brief": {
                "title": "Research official FastAPI behavior",
                "instructions": "Verify official behavior before another repair round.",
                "context": {
                    "observed": "dependency override still returns 500",
                    "expected": "test should return mocked dependency result",
                    "tried": "fixture-level override already attempted",
                    "need": "official behavior for override timing",
                },
            },
        }
    )

    assert "Action: felo_research" in prompt
    assert "Title: Research official FastAPI behavior" in prompt
    assert "Summary: framework behavior unclear" in prompt
    assert "Reasons: external_signal, repeated_failure" in prompt
    assert "- observed: dependency override still returns 500" in prompt
    assert "Deliverable:" in prompt


def test_build_prompt_defaults_to_gemini_repair_when_action_missing():
    prompt = build_gemini_prompt({"action_brief": {}})
    assert "Action: gemini_repair" in prompt
