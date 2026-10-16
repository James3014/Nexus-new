from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sf_final_local_skill_compare import build_sf_final_local_skill_compare, main


def _write_skill(root: Path, skill_id: str, body: str) -> Path:
    path = root / skill_id / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _settlement() -> dict:
    return {
        "status": "PASS",
        "settlement_rows": [
            {"capability": "codeintel", "current_primary_skill_id": "current-codeintel"},
            {"capability": "artifact_gate", "current_primary_skill_id": "current-artifact"},
        ],
    }


def _compare(candidate_path: Path, blocked_path: Path) -> dict:
    return {
        "status": "PASS",
        "compare_rows": [
            {
                "capability": "codeintel",
                "baseline_arm": {"skill_ids": ["current-codeintel"]},
                "candidate_skill_id": "candidate-codeintel",
                "candidate_role": "Scout",
                "canonical_source_path": str(candidate_path),
                "decision": "READY_FOR_LIVE_COMPARE",
                "deterministic_precheck": {"status": "PASS", "blockers": []},
            },
            {
                "capability": "artifact_gate",
                "baseline_arm": {"skill_ids": ["current-artifact"]},
                "candidate_skill_id": "blocked-artifact",
                "candidate_role": "Audit",
                "canonical_source_path": str(blocked_path),
                "decision": "REJECT_PRECHECK",
                "deterministic_precheck": {"status": "RETURN", "blockers": ["quarantine_tier_blocked"]},
            },
        ],
    }


def test_local_skill_compare_recommends_only_stronger_unblocked_candidate(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "current-codeintel", "Code scan. Verify output.")
    candidate_path = _write_skill(
        root,
        "candidate-codeintel",
        """
        # CodeIntel Scout
        Use for codeintel code symbol scan repo impact complexity analysis.
        Steps:
        1. Scan symbols.
        2. Verify impact.
        3. Produce evidence receipt gate output.
        Do not skip tests. Fail-closed on missing evidence. Include rollback risk and CI notes.
        Use this skill when code changes need symbol-aware context, impact review, dependency scan,
        and precise implementation evidence. The output must include touched symbols, affected files,
        verification commands, confidence limits, and a receipt-backed recommendation.
        It should separate scout facts from logic decisions and preserve the artifact trail.
        """,
    )
    _write_skill(root, "current-artifact", "Artifact evidence gate verify test receipt.")
    blocked_path = _write_skill(root, "blocked-artifact", "Artifact evidence audit gate receipt.")

    payload = build_sf_final_local_skill_compare(
        settlement=_settlement(),
        compare_report=_compare(candidate_path, blocked_path),
        skill_roots=[root],
        replace_margin=15,
    )

    assert payload["status"] == "PASS"
    assert payload["summary"]["replacement_candidate_count"] == 1
    decisions = {row["capability"]: row for row in payload["capability_decisions"]}
    assert decisions["codeintel"]["decision"] == "REPLACE_PRIMARY_LOCAL_CANDIDATE"
    assert decisions["codeintel"]["recommended_skill_id"] == "candidate-codeintel"
    assert decisions["artifact_gate"]["decision"] == "KEEP_CURRENT"

    rows = {row["candidate_skill_id"]: row for row in payload["compare_rows"]}
    assert rows["blocked-artifact"]["decision"] == "REJECT_LOCAL_PRECHECK"
    assert rows["candidate-codeintel"]["runtime_update_allowed"] is False


def test_local_skill_compare_cli_writes_report(tmp_path: Path, capsys) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "current-codeintel", "Code scan. Verify output.")
    candidate_path = _write_skill(
        root,
        "candidate-codeintel",
        """
        codeintel code symbol scan repo impact complexity steps verify test evidence receipt gate fail-closed CI.
        Use for symbol-aware repository scanning, dependency impact review, context collection, and
        implementation evidence. Include changed symbols, affected tests, confidence limits, rollback risk,
        gate status, and artifact references. Keep scout evidence separate from final repair decisions.
        Workflow steps: inspect imports, identify callers, compare changed paths, verify test coverage,
        and produce a concise output with receipt links. Do not claim readiness when evidence is absent.
        """,
    )
    blocked_path = _write_skill(root, "blocked-artifact", "Artifact evidence audit gate receipt.")
    settlement_path = tmp_path / "settlement.json"
    compare_path = tmp_path / "compare.json"
    output_path = tmp_path / "local_compare.json"
    settlement_path.write_text(json.dumps(_settlement()), encoding="utf-8")
    compare_path.write_text(json.dumps(_compare(candidate_path, blocked_path)), encoding="utf-8")

    rc = main(
        [
            "--settlement",
            str(settlement_path),
            "--compare",
            str(compare_path),
            "--skill-root",
            str(root),
            "--output",
            str(output_path),
        ]
    )
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output_path.exists()
    assert captured["status"] == "PASS"
    assert captured["replacement_candidate_count"] == 1
