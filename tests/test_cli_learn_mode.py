import json
from click.testing import CliRunner
from unittest.mock import MagicMock

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
            "--evidence-file",
            ".nexus/reports/learn/evidence_ingest.json",
            "--output-json",
        ],
    )
    assert ingest.exit_code == 0, ingest.output
    ingest_payload = json.loads(ingest.output)
    assert ingest_payload["claims_count"] >= 1
    assert (tmp_path / ".nexus" / "knowledge" / "learn_claims.jsonl").exists()
    assert (tmp_path / ".nexus" / "reports" / "learn" / "evidence_ingest.json").exists()

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
            "--question-count",
            "3",
            "--no-auto-research",
            "--swarm-mode",
            "--swarm-max-parallel",
            "2",
            "--per-source-timeout-sec",
            "10",
            "--evidence-file",
            ".nexus/reports/learn/evidence_converge.json",
            "--output-json",
        ],
    )
    assert converge.exit_code == 0, converge.output
    converge_payload = json.loads(converge.output)
    assert converge_payload["status"] == "SUCCESS"
    assert converge_payload["self_question_pass_rate"] >= 0.5
    assert "question_set" in converge_payload
    assert "answered_questions" in converge_payload
    assert "swarm" in converge_payload
    assert "round_activity" in converge_payload
    assert (tmp_path / ".nexus" / "reports" / "learn" / "evidence_converge.json").exists()

    learn_report = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:report",
            "--topic",
            "nexus pipeline",
            "--output-json",
        ],
    )
    assert learn_report.exit_code == 0, learn_report.output
    report_payload = json.loads(learn_report.output)
    assert report_payload["status"] == "SUCCESS"
    assert report_payload["claims_count"] >= 1
    assert report_payload["citation_valid_ratio"] > 0.0
    assert "topic_packs" in report_payload
    assert "high_strength_claims" in report_payload
    assert "stale_claims_count" in report_payload
    assert "question_set" in report_payload
    assert "answered_questions" in report_payload

    ask = runner.invoke(
        nexus,
        [
            "nexus",
            "ask",
            "--topic",
            "nexus pipeline",
            "--question",
            "What does Nexus learn mode do?",
            "--top-k",
            "3",
            "--min-evidence",
            "1",
            "--evidence-file",
            ".nexus/reports/learn/evidence_ask.json",
            "--output-json",
        ],
    )
    assert ask.exit_code == 0, ask.output
    ask_payload = json.loads(ask.output)
    assert ask_payload["status"] == "ANSWERED"
    assert ask_payload["citations"]
    assert "#span=" in ask_payload["answer"]
    assert (tmp_path / ".nexus" / "reports" / "learn" / "evidence_ask.json").exists()


def test_learn_ask_returns_unknown_without_cited_claims(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "REPO_ROOT", tmp_path)

    ask = runner.invoke(
        nexus,
        [
            "nexus",
            "ask",
            "--topic",
            "nexus",
            "--question",
            "nonexistent-domain-token-zzz",
            "--output-json",
        ],
    )
    assert ask.exit_code == 0, ask.output
    payload = json.loads(ask.output)
    assert payload["status"] == "UNKNOWN"
    assert payload["answer"] == "UNKNOWN"


def test_learn_ask_returns_unknown_when_min_evidence_not_met(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "REPO_ROOT", tmp_path)

    claims_path = tmp_path / ".nexus" / "knowledge" / "learn_claims.jsonl"
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims_path.write_text(
        json.dumps(
            {
                "claim": "Nexus learn mode stores cited claims.",
                "source_url": "file:///tmp/src.md",
                "citation_span": [0, 35],
                "topic_tags": ["nexus", "learn"],
                "created_at": "2026-04-14T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    ask = runner.invoke(
        nexus,
        [
            "nexus",
            "ask",
            "--topic",
            "nexus learn mode",
            "--question",
            "nexus learn mode",
            "--min-evidence",
            "2",
            "--output-json",
        ],
    )
    assert ask.exit_code == 0, ask.output
    payload = json.loads(ask.output)
    assert payload["status"] == "UNKNOWN"
    assert payload["reason"] == "insufficient_cited_claims"


def test_learn_ask_returns_conflict_for_contradictory_claims(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "REPO_ROOT", tmp_path)

    claims_path = tmp_path / ".nexus" / "knowledge" / "learn_claims.jsonl"
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims = [
        {
            "claim": "Repo Scout supports audio review for repository analysis.",
            "source_url": "file:///tmp/a.md",
            "citation_span": [0, 55],
            "topic_tags": ["repo", "scout", "audio", "review"],
            "created_at": "2026-04-14T00:00:00+00:00",
            "topic_pack": "repo_scout",
            "evidence_strength": "high",
        },
        {
            "claim": "Repo Scout does not support audio review for repository analysis.",
            "source_url": "file:///tmp/b.md",
            "citation_span": [0, 63],
            "topic_tags": ["repo", "scout", "audio", "review"],
            "created_at": "2026-04-14T00:00:00+00:00",
            "topic_pack": "repo_scout",
            "evidence_strength": "high",
        },
    ]
    claims_path.write_text("\n".join(json.dumps(c) for c in claims) + "\n", encoding="utf-8")

    ask = runner.invoke(
        nexus,
        [
            "nexus",
            "ask",
            "--topic",
            "repo scout",
            "--question",
            "Does repo scout support audio review?",
            "--output-json",
        ],
    )
    assert ask.exit_code == 0, ask.output
    payload = json.loads(ask.output)
    assert payload["status"] == "CONFLICT"
    assert payload["reason"] == "conflicting_cited_claims"
    assert payload["conflicts"]


def test_learn_gate_runs_acceptance_contract_and_ci(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "REPO_ROOT", tmp_path)

    claims_path = tmp_path / ".nexus" / "knowledge" / "learn_claims.jsonl"
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims_path.write_text(
        json.dumps(
            {
                "claim": "Nexus learn gate validates evidence chain.",
                "source_url": "file:///tmp/src.md",
                "citation_span": [0, 40],
                "topic_tags": ["nexus", "learn", "gate"],
                "created_at": "2026-04-14T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    contract = tmp_path / ".nexus" / "config" / "task_contract.example.json"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text("{}", encoding="utf-8")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", fake_run)

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:gate",
            "--topic",
            "nexus learn",
            "--pass-threshold",
            "0.3",
            "--claims-min",
            "1",
            "--contract-file",
            str(contract),
        ],
    )
    assert result.exit_code == 0, result.output
    assert any("acceptance-check" in " ".join(map(str, c)) for c in calls)
    assert any("contract-check" in " ".join(map(str, c)) for c in calls)
    assert any("ci_gate.py" in " ".join(map(str, c)) for c in calls)


def test_learn_benchmark_reports_best_config(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "REPO_ROOT", tmp_path)

    source_file = tmp_path / "source.md"
    source_file.write_text(
        (
            "Repo Scout analyzes repositories and supports audio review. "
            "It can discover competitors and summarize repository structure. "
            "There is no database migration workflow documented in this skill."
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question": "What does Repo Scout do?",
                        "expected_status": "ANSWERED",
                        "expected_keywords": ["analyzes repositories"],
                    },
                    {
                        "question": "What database migration workflow is documented?",
                        "expected_status": "UNKNOWN",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:benchmark",
            "--manifest-file",
            str(manifest),
            "--source",
            "repo:repo-scout",
            "--source-file",
            str(source_file),
            "--topic",
            "repo-scout",
            "--output-json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "SUCCESS"
    assert "baseline" in payload
    assert "best" in payload
    assert payload["best"]["success_rate"] >= payload["baseline"]["success_rate"]
