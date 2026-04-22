import json
from click.testing import CliRunner
from unittest.mock import MagicMock

from scripts.engine import nexus_cli
from scripts.engine.nexus_cli import nexus


def test_learn_mode_ingest_converge_and_ask(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

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
            "--markdown-report-file",
            ".nexus/reports/learn/learn_ingest.md",
            "--evidence-file",
            ".nexus/reports/learn/evidence_ingest.json",
            "--output-json",
        ],
    )
    assert ingest.exit_code == 0, ingest.output
    ingest_payload = json.loads(ingest.output)
    assert ingest_payload["claims_count"] >= 1
    assert ingest_payload["semantic_status"] == "VERIFIED"
    assert "channel_counts" in ingest_payload
    assert "tactical_data" in ingest_payload["channel_counts"]
    assert "governance_principles" in ingest_payload["channel_counts"]
    assert (tmp_path / ".nexus" / "knowledge" / "learn_claims.jsonl").exists()
    assert (tmp_path / ".nexus" / "reports" / "learn" / "evidence_ingest.json").exists()
    ingest_md = (tmp_path / ".nexus" / "reports" / "learn" / "learn_ingest.md")
    assert ingest_md.exists()
    ingest_md_text = ingest_md.read_text(encoding="utf-8")
    assert "[Task]" in ingest_md_text
    assert "[Data]" in ingest_md_text
    assert "[Evidence]" in ingest_md_text
    assert "[Residual Debt]" in ingest_md_text

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
    assert "phase_learning_bridge" in converge_payload
    assert converge_payload["phase_learning_bridge"]["entries_written"] == 6
    assert (tmp_path / ".nexus" / "reports" / "learn" / "evidence_converge.json").exists()
    assert (tmp_path / ".nexus" / "reports" / "learn" / "phase_writeback.jsonl").exists()
    assert (tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").exists()

    learn_report = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:report",
            "--topic",
            "nexus pipeline",
            "--markdown-report-file",
            ".nexus/reports/learn/learn_report.md",
            "--output-json",
        ],
    )
    assert learn_report.exit_code == 0, learn_report.output
    report_payload = json.loads(learn_report.output)
    assert report_payload["status"] == "SUCCESS"
    assert report_payload["semantic_status"] == "VERIFIED"
    assert report_payload["claims_count"] >= 1
    assert report_payload["citation_valid_ratio"] > 0.0
    assert "topic_packs" in report_payload
    assert "high_strength_claims" in report_payload
    assert "stale_claims_count" in report_payload
    assert "question_set" in report_payload
    assert "answered_questions" in report_payload
    report_md = (tmp_path / ".nexus" / "reports" / "learn" / "learn_report.md")
    assert report_md.exists()
    report_md_text = report_md.read_text(encoding="utf-8")
    assert "[Task]" in report_md_text
    assert "[Data]" in report_md_text
    assert "[Evidence]" in report_md_text
    assert "[Residual Debt]" in report_md_text

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


def test_learn_ingest_fails_closed_when_semantic_contract_unverified(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)
    monkeypatch.setattr(
        nexus_cli,
        "_evaluate_learn_semantic_contract",
        lambda **kwargs: {
            "semantic_status": "UNVERIFIED",
            "semantic_failures": ["missing_dual_channel_fields"],
        },
    )

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:ingest",
            "--source",
            "alpha-keyword",
            "--topic",
            "nexus",
            "--output-json",
        ],
    )
    assert result.exit_code != 0
    assert "missing_dual_channel_fields" in result.output


def test_learn_ask_returns_unknown_without_cited_claims(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

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
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

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
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

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
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

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
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

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
    assert "answer_precision" in payload["baseline"]
    assert "unknown_accuracy" in payload["baseline"]
    assert "avg_token_coverage" in payload["baseline"]


def test_learn_register_source_and_refresh(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

    source_file = tmp_path / "source.md"
    source_file.write_text(
        "OpenHarness evaluates agents and benchmark dimensions with cited evidence.",
        encoding="utf-8",
    )

    reg = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:register-source",
            "--topic",
            "openharness",
            "--source",
            "repo:HKUDS/OpenHarness",
            "--source-file",
            str(source_file),
            "--refresh-after-days",
            "1",
            "--priority",
            "high",
            "--output-json",
        ],
    )
    assert reg.exit_code == 0, reg.output
    reg_payload = json.loads(reg.output)
    assert reg_payload["status"] == "SUCCESS"
    assert (tmp_path / ".nexus" / "knowledge" / "learn_sources.jsonl").exists()

    refresh = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:refresh",
            "--topic",
            "openharness",
            "--all",
            "--output-json",
        ],
    )
    assert refresh.exit_code == 0, refresh.output
    refresh_payload = json.loads(refresh.output)
    assert refresh_payload["status"] == "SUCCESS"
    assert refresh_payload["refreshed_count"] == 1


def test_learn_ask_unknown_writes_benchmark_candidate(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

    source_file = tmp_path / "source.md"
    source_file.write_text(
        "Repo Scout discovers repository structure and summarizes codebases with cited evidence.",
        encoding="utf-8",
    )

    ingest = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:ingest",
            "--source",
            "repo:repo-scout",
            "--source-file",
            str(source_file),
            "--topic",
            "repo-scout",
            "--output-json",
        ],
    )
    assert ingest.exit_code == 0, ingest.output

    ask = runner.invoke(
        nexus,
        [
            "nexus",
            "ask",
            "--topic",
            "repo-scout",
            "--question",
            "What Kubernetes CRD schema and migration workflow does this repo implement?",
            "--output-json",
        ],
    )
    assert ask.exit_code == 0, ask.output
    ask_payload = json.loads(ask.output)
    assert ask_payload["status"] == "UNKNOWN"

    candidates_path = tmp_path / ".nexus" / "knowledge" / "learn_benchmark_candidates.jsonl"
    assert candidates_path.exists()
    rows = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert rows[-1]["topic"] == "repo-scout"
    assert rows[-1]["actual_status"] == "UNKNOWN"


def test_learn_refresh_plan_marks_due_sources(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

    sources_path = tmp_path / ".nexus" / "knowledge" / "learn_sources.jsonl"
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    sources_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "topic": "openharness",
                        "source": "repo:HKUDS/OpenHarness",
                        "source_file": "",
                        "refresh_after_days": 1,
                        "priority": "high",
                        "last_ingested_at": "2026-04-10T00:00:00+00:00",
                        "last_refreshed_at": "2026-04-10T00:00:00+00:00",
                        "last_claim_count": 100,
                    }
                ),
                json.dumps(
                    {
                        "topic": "repo-scout",
                        "source": "repo:BingJyun/repo-scout-skill",
                        "source_file": "",
                        "refresh_after_days": 14,
                        "priority": "medium",
                        "last_ingested_at": "2026-04-15T00:00:00+00:00",
                        "last_refreshed_at": "2026-04-15T00:00:00+00:00",
                        "last_claim_count": 50,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    plan = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:refresh-plan",
            "--due-within-days",
            "0",
            "--output-json",
        ],
    )
    assert plan.exit_code == 0, plan.output
    payload = json.loads(plan.output)
    assert payload["status"] == "SUCCESS"
    assert payload["due_count"] == 1
    assert payload["not_due_count"] == 1
    assert payload["due"][0]["topic"] == "openharness"


def test_learn_benchmark_curate_generates_manifest(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

    candidates_path = tmp_path / ".nexus" / "knowledge" / "learn_benchmark_candidates.jsonl"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "topic": "openharness",
                        "question": "What benchmark dimensions does OpenHarness evaluate?",
                        "actual_status": "ANSWERED",
                        "reason": "answered_with_citations",
                        "token_coverage": 0.8,
                        "created_at": "2026-04-15T00:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "topic": "openharness",
                        "question": "What benchmark dimensions does OpenHarness evaluate?",
                        "actual_status": "ANSWERED",
                        "reason": "answered_with_citations",
                        "token_coverage": 0.82,
                        "created_at": "2026-04-15T01:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "topic": "openharness",
                        "question": "What PostgreSQL migration workflow is used?",
                        "actual_status": "UNKNOWN",
                        "reason": "insufficient_token_coverage",
                        "token_coverage": 0.2,
                        "created_at": "2026-04-15T01:10:00+00:00",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:benchmark-curate",
            "--topic",
            "openharness",
            "--max-questions",
            "10",
            "--manifest-file",
            "docs/research/learn_benchmark_curated.json",
            "--output-json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "SUCCESS"
    assert payload["selected_count"] >= 2

    manifest = tmp_path / "docs" / "research" / "learn_benchmark_curated.json"
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(manifest_payload["questions"]) >= 2


def test_learn_phase_slo_command_outputs_summary(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

    phase_log = tmp_path / ".nexus" / "reports" / "learn" / "phase_writeback.jsonl"
    phase_log.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for phase in ["P", "X", "D", "R", "A", "C"]:
        entries.append(
            {
                "timestamp": "2026-04-15T00:00:00+00:00",
                "topic": "nexus",
                "phase": phase,
                "phase_status": "SUCCESS",
                "route": {"mode": "light"},
                "writeback_policy": {"required": True, "policy": "required"},
                "writeback_done": True,
            }
        )
    phase_log.write_text("\n".join(json.dumps(row) for row in entries) + "\n", encoding="utf-8")

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:phase-slo",
            "--window",
            "100",
            "--output-json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "SUCCESS"
    assert payload["phase_slo_pass"] is True
    assert payload["global"]["required_done_ratio"] >= 0.95


def test_learn_phase_kpi_command_outputs_summary(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)

    phase_log = tmp_path / ".nexus" / "reports" / "learn" / "phase_writeback.jsonl"
    phase_log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "timestamp": "2026-04-15T00:00:00+00:00",
            "topic": "nexus",
            "phase": "P",
            "phase_status": "SUCCESS",
            "route": {"mode": "light"},
            "writeback_policy": {"required": True, "policy": "required"},
            "writeback_done": True,
        },
        {
            "timestamp": "2026-04-15T00:01:00+00:00",
            "topic": "nexus",
            "phase": "R",
            "phase_status": "PARTIAL",
            "route": {"mode": "research"},
            "writeback_policy": {"required": True, "policy": "required"},
            "writeback_done": False,
        },
    ]
    phase_log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    result = runner.invoke(
        nexus,
        [
            "nexus",
            "learn:phase-kpi",
            "--window",
            "100",
            "--output-json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "SUCCESS"
    assert payload["total_records"] == 2
    assert "P" in payload["phases"]
    assert "R" in payload["phases"]
    assert payload["mode_breakdown"]["light"] == 1
    assert payload["mode_breakdown"]["research"] == 1
