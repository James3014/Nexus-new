import json
from click.testing import CliRunner

from scripts.engine import nexus_cli
from scripts.engine.nexus_cli import nexus


def test_learn_mode_ingest_converge_and_ask(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "REPO_ROOT", tmp_path)

    source_file = tmp_path / "source.md"
    source_file.write_text(
        (
            "Nexus uses a six-phase pipeline for reliable software delivery. "
            "Learn mode extracts cited claims and stores them in machine-readable form. "
            "MemPalace verifies candidate knowledge before durable writeback."
        ),
        encoding="utf-8",
    )

    ingest = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:ingest",
            "--source",
            "repo:nexus",
            "--source-file",
            str(source_file),
            "--topic",
            "nexus",
            "--report-file",
            ".nexus/reports/learn/learn_report.json",
            "--output-json",
        ],
    )
    assert ingest.exit_code == 0, ingest.output
    ingest_payload = json.loads(ingest.output)
    assert ingest_payload["claims_count"] >= 1
    assert (tmp_path / ".nexus" / "knowledge" / "learn_claims.jsonl").exists()

    converge = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:converge",
            "--topic",
            "nexus pipeline",
            "--max-rounds",
            "2",
            "--pass-threshold",
            "0.5",
            "--output-json",
        ],
    )
    assert converge.exit_code == 0, converge.output
    converge_payload = json.loads(converge.output)
    assert converge_payload["status"] == "SUCCESS"
    assert converge_payload["self_question_pass_rate"] >= 0.5

    ask = runner.invoke(
        nexus,
        [
            "nexus",
            "ask",
            "--topic",
            "What does Nexus learn mode do?",
            "--top-k",
            "3",
            "--output-json",
        ],
    )
    assert ask.exit_code == 0, ask.output
    ask_payload = json.loads(ask.output)
    assert ask_payload["status"] == "ANSWERED"
    assert ask_payload["citations"]
    assert "#span=" in ask_payload["answer"]


def test_learn_ask_returns_unknown_without_cited_claims(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "REPO_ROOT", tmp_path)

    ask = runner.invoke(
        nexus,
        [
            "nexus",
            "ask",
            "--topic",
            "nonexistent-domain-token-zzz",
            "--output-json",
        ],
    )
    assert ask.exit_code == 0, ask.output
    payload = json.loads(ask.output)
    assert payload["status"] == "UNKNOWN"
    assert payload["answer"] == "UNKNOWN"

