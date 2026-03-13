from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.reporter import Reporter


def test_markdown_report_includes_escalation_and_action_brief(tmp_path):
    report_path = tmp_path / "report.md"

    Reporter.write_markdown_report(
        report_path,
        {
            "status": "FAIL",
            "summary": "validator schema still mismatched",
            "violations": [
                {
                    "severity": "MAJOR",
                    "type": "SCHEMA",
                    "file": "scripts/core/state_contracts.py",
                    "line": 12,
                    "reason": "missing default field",
                    "suggestion": "add a compatibility-safe default",
                }
            ],
            "next_action": "felo_research",
            "next_actor": "felo",
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
        },
        total_tokens=1234,
    )

    text = report_path.read_text(encoding="utf-8")

    assert "**Status**: FAIL" in text
    assert "**Total Tokens**: 1,234" in text
    assert "## Next Step" in text
    assert "- **Action**: `felo_research`" in text
    assert "- **Actor**: `felo`" in text
    assert "- **Reasons**: `external_signal`, `repeated_failure`" in text
    assert "### Research official FastAPI behavior" in text
    assert "- **observed**: dependency override still returns 500" in text


def test_markdown_report_omits_next_step_section_when_not_present(tmp_path):
    report_path = tmp_path / "report.md"

    Reporter.write_markdown_report(
        report_path,
        {
            "status": "PASS",
            "summary": "all checks passed",
            "violations": [],
        },
    )

    text = report_path.read_text(encoding="utf-8")

    assert "## Next Step" not in text
    assert "## Violations" in text


def test_write_action_sidecar_exports_machine_readable_handoff(tmp_path):
    action_path = tmp_path / "next_action.json"

    Reporter.write_action_sidecar(
        action_path,
        {
            "status": "FAIL",
            "next_action": "codex_patch",
            "next_actor": "codex",
            "escalation_reasons": ["codex_patch_threshold_reached"],
            "action_brief": {
                "title": "Escalate to definitive patch",
                "instructions": "Produce a compile-ready unified diff.",
                "context": {
                    "files": ["scripts/codex_loop_brain.py"],
                    "observed": "same failing assertion after multiple retries",
                },
            },
        },
    )

    payload = action_path.read_text(encoding="utf-8")

    assert '"next_action": "codex_patch"' in payload
    assert '"next_actor": "codex"' in payload
    assert '"title": "Escalate to definitive patch"' in payload
