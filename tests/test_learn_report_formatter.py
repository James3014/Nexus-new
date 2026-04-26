import json

from click.testing import CliRunner

from scripts.engine.nexus_cli import nexus


def test_format_unresolved_questions_supports_dict_and_list_items():
    from scripts.engine import nexus_cli

    unresolved = [
        "plain text question",
        {"question": "missing rollback path", "phase": "R"},
        ["nested", "array"],
        {"unknown": "shape"},
    ]

    rendered = nexus_cli._format_unresolved_questions_for_debt(unresolved)

    assert "plain text question" in rendered
    assert "missing rollback path" in rendered
    assert "[nested, array]" in rendered
    assert '{"unknown": "shape"}' in rendered


def test_learn_report_does_not_crash_on_structured_unresolved_questions(tmp_path, monkeypatch):
    class FakeLearnModeService:
        def __init__(self, *_args, **_kwargs):
            pass

        def build_report(self, **_kwargs):
            return {
                "sources_count": 1,
                "claims_count": 3,
                "coverage": 0.8,
                "converged": False,
                "citation_valid_ratio": 1.0,
                "unresolved_questions": [
                    {"question": "need ADR check", "owner": "guardrail"},
                    ["runtime", "isolation"],
                    "sync wiki truth page",
                ],
            }

    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    monkeypatch.setattr("nexus.research.learn_mode.LearnModeService", FakeLearnModeService)
    monkeypatch.setattr(
        "scripts.engine.nexus_cli._evaluate_learn_semantic_contract",
        lambda **_kwargs: {"semantic_status": "VERIFIED", "semantic_failures": []},
    )

    runner = CliRunner()
    result = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:report",
            "--topic",
            "nexus-governance",
            "--output-json",
            "--report-file",
            ".nexus/reports/learn/learn_report.json",
            "--markdown-report-file",
            ".nexus/reports/learn/learn_report.md",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["semantic_status"] == "VERIFIED"
    assert payload["claims_count"] == 3
