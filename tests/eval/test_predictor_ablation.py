"""Unit tests for scripts/eval/run_predictor_ablation.py. No model calls."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import run_predictor_ablation as ablation  # noqa: E402

LATENT_ENV = "NEXUS_LATENT_PREDICTOR"
LEWM_ENV = "NEXUS_LEWM_PREDICTOR"


def _entry(name, consulted, changed, path="decision_site_probe"):
    return {"name": name, "consulted": consulted, "changed_decision": changed, "path": path}


def test_arm_env_sets_and_restores(monkeypatch):
    monkeypatch.setenv(LATENT_ENV, "keep")
    monkeypatch.delenv(LEWM_ENV, raising=False)
    with ablation.arm_env("lewm_off"):
        assert os.environ[LATENT_ENV] == "on"
        assert os.environ[LEWM_ENV] == "off"
    assert os.environ[LATENT_ENV] == "keep"
    assert LEWM_ENV not in os.environ


def test_arm_definitions_cover_the_four_arms():
    assert set(ablation.PREDICTOR_ARMS) == {"both_on", "latent_off", "lewm_off", "both_off"}
    assert ablation.PREDICTOR_ARMS["both_off"] == ("off", "off")


def test_count_influence_counts_consulted_and_changed():
    counts = ablation.count_influence([
        _entry("latent_predictor_v20", True, True),
        _entry("latent_predictor_v20", True, False),
        _entry("latent_predictor_v20", False, False),
        _entry("lewm_predictor", True, False),
    ])
    assert counts["latent_predictor_v20"] == {"entries": 3, "consulted": 2, "changed_decision": 1}
    assert counts["lewm_predictor"] == {"entries": 1, "consulted": 1, "changed_decision": 0}


def test_scorecard_probe_only_reports_counts_by_arm_and_path():
    rows = [
        {
            "predictor_arm": arm,
            "predictor_influence": [_entry("lewm_predictor", True, arm == "both_on")],
        }
        for arm in ablation.PREDICTOR_ARMS
    ]
    card = ablation.build_scorecard(rows, 1, "m", probe_only=True)
    assert card["local_heal_executed"] is False
    assert card["memory_enabled_in_all_arms"] is False
    assert card["predictor_influence"]["both_on"]["lewm_predictor"]["changed_decision"] == 1
    assert card["predictor_influence"]["both_off"]["lewm_predictor"]["changed_decision"] == 0
    by_path = card["predictor_influence_by_path"]["both_on"]["decision_site_probe"]
    assert by_path["lewm_predictor"]["consulted"] == 1
    assert "paired_uplift_vs_both_off" not in card


def test_probe_only_main_writes_rows_and_scorecard(tmp_path):
    tasks = tmp_path / "tasks"
    task = tasks / "toy-0"
    task.mkdir(parents=True)
    (task / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (task / "repro.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
    (task / "task.json").write_text(
        json.dumps({
            "id": "toy-0",
            "bug_class": "toy",
            "variant": "0",
            "problem_statement": "f() returns 1; the NexusState serialization is wrong",
            "target_file": "m.py",
            "repro_file": "repro.py",
        }),
        encoding="utf-8",
    )
    artifacts = tmp_path / "artifacts"
    rc = ablation.main([
        "--probe-only",
        "--tasks-dir",
        str(tasks),
        "--artifact-root",
        str(artifacts),
        "--run-id",
        "t1",
    ])
    assert rc == 0
    rows = [json.loads(line) for line in (artifacts / "t1" / "rows.jsonl").read_text().splitlines()]
    assert [r["predictor_arm"] for r in rows] == list(ablation.PREDICTOR_ARMS)
    card = json.loads((artifacts / "t1" / "scorecard.json").read_text())
    influence = card["predictor_influence"]
    # The probe forces sim_lewm, but LeWM was archived 2026-10-12: it is never consulted.
    assert influence["both_on"]["lewm_predictor"]["consulted"] == 0
    assert influence["both_off"]["lewm_predictor"]["consulted"] == 0
    assert influence["both_off"]["latent_predictor_v20"]["consulted"] == 0
    assert influence["latent_off"]["lewm_predictor"]["consulted"] == 0
    assert influence["lewm_off"]["latent_predictor_v20"]["consulted"] >= 1


def test_arms_must_include_baseline():
    with pytest.raises(SystemExit):
        ablation.parse_args(["--arms", "both_on"])
