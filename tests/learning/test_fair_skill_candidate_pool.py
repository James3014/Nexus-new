import json
from pathlib import Path

from nexus.learning.fair_skill_candidate_pool import build_fair_skill_candidate_pool, write_fair_skill_candidate_pool


def _status_report():
    return {
        "schema": "nexus.skill_status.v1",
        "skills": [
            {
                "name": "nexus-tdd",
                "path": "/repo/.agents/skills/tdd/SKILL.md",
                "root": "nexus_repo",
                "skill_status": "nexus_curated_candidate",
                "action": "eligible_for_capability_mount_review",
                "description": "Load when repairing code with tests.",
                "capability_mount": "repair_and_coding",
                "sha256": "aaa",
                "reason_codes": ["repo_local_nexus_skill"],
            },
            {
                "name": "hermes-debug",
                "path": "/Users/jameschen/Workspace/hermes-agent/skills/debug/SKILL.md",
                "root": "hermes",
                "skill_status": "external_reference_candidate",
                "action": "reference_only_until_imported",
                "description": "Load when debugging failures.",
                "capability_mount": "reference:repair_and_coding",
                "sha256": "bbb",
                "reason_codes": ["structured_hermes_reference_catalog"],
            },
            {
                "name": "generated-candidate",
                "path": "/Users/jameschen/.agents/skills/generated/SKILL.md",
                "root": "agents",
                "skill_status": "candidate_quarantine",
                "action": "review_before_promotion",
                "description": "Generated candidate.",
                "capability_mount": "reference:repair_and_coding",
                "sha256": "ccc",
                "reason_codes": ["generated_or_candidate_inbox"],
            },
        ],
    }


def test_fair_pool_separates_ablation_from_runtime_eligibility():
    pool = build_fair_skill_candidate_pool(_status_report())
    by_id = {candidate["skill_id"]: candidate for candidate in pool["candidates"]}

    assert pool["status"] == "PASS"
    assert by_id["nexus-tdd"]["ablation_eligible"] is True
    assert by_id["nexus-tdd"]["runtime_eligible"] is True
    assert by_id["hermes-debug"]["ablation_eligible"] is True
    assert by_id["hermes-debug"]["runtime_eligible"] is False
    assert by_id["generated-candidate"]["ablation_eligible"] is False
    assert by_id["generated-candidate"]["runtime_eligible"] is False
    assert by_id["generated-candidate"]["quarantine_reason"] == "status:candidate_quarantine"


def test_fair_pool_records_duplicate_shadow_policy():
    report = _status_report()
    report["skills"].append(
        {
            "name": "nexus-tdd",
            "path": "/tmp/worktree/.agents/skills/tdd/SKILL.md",
            "root": "codex_worktrees",
            "skill_status": "worktree_copy_quarantine",
            "action": "do_not_load",
            "description": "Copy.",
            "capability_mount": None,
            "sha256": "ddd",
            "reason_codes": ["non_canonical_worktree_copy"],
        }
    )

    pool = build_fair_skill_candidate_pool(report)
    copies = [candidate for candidate in pool["candidates"] if candidate["skill_id"] == "nexus-tdd"]

    assert {candidate["shadow_policy"]["duplicate_count"] for candidate in copies} == {2}
    assert any(candidate["shadow_policy"]["shadowed"] for candidate in copies)
    assert all(candidate["shadow_policy"]["canonical_path"] == "/repo/.agents/skills/tdd/SKILL.md" for candidate in copies)


def test_write_fair_pool_outputs_receipt_ready_json(tmp_path: Path):
    status_report = tmp_path / "status.json"
    output = tmp_path / "pool.json"
    status_report.write_text(json.dumps(_status_report()), encoding="utf-8")

    pool = write_fair_skill_candidate_pool(status_report_path=status_report, output_path=output)

    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema"] == "nexus.fair_skill_candidate_pool.v1"
    assert saved["summary"]["ablation_eligible_count"] == 2
    assert saved["summary"]["runtime_eligible_count"] == 1
    assert pool == saved
