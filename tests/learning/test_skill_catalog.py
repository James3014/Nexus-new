import json
from pathlib import Path

from nexus.learning.skill_catalog import SkillCatalog


def _write_status_report(path: Path) -> None:
    payload = {
        "schema": "nexus.skill_status.v1",
        "skills": [
            {
                "name": "nexus-benchmark-public-report",
                "path": "/repo/.agents/skills/nexus-benchmark-public-report/SKILL.md",
                "root": "nexus_repo",
                "skill_status": "nexus_curated_candidate",
                "test_level": "routing_plus_e2e",
                "action": "eligible_for_capability_mount_review",
                "capability_mount": "benchmark_and_promotion",
                "reason_codes": ["repo_local_nexus_skill"],
            },
            {
                "name": "candidate-skill-from-run-001",
                "path": "/Users/jameschen/.agents/skills/candidate-skill-from-run-001/SKILL.md",
                "root": "agents",
                "skill_status": "candidate_quarantine",
                "test_level": "quarantine",
                "action": "review_before_promotion",
                "capability_mount": None,
                "reason_codes": ["generated_or_candidate_inbox"],
            },
            {
                "name": "hermes-debugging",
                "path": "/Users/jameschen/Workspace/hermes-agent/skills/debugging/SKILL.md",
                "root": "hermes",
                "skill_status": "external_reference_candidate",
                "test_level": "routing_reference",
                "action": "reference_only_until_imported",
                "capability_mount": "reference:repair_and_coding",
                "reason_codes": ["structured_hermes_reference_catalog"],
            },
            {
                "name": "create-plan",
                "path": "/repo/.agents/skills/create-plan/SKILL.md",
                "root": "nexus_repo",
                "skill_status": "nexus_repo_local_candidate",
                "test_level": "sf_promotion_seal",
                "action": "ablation_only_promotion_seal",
                "capability_mount": "reference:autoreason",
                "reason_codes": ["repo_local_materialized_external_skill"],
            },
            {
                "name": "codex-vendor-skill",
                "path": "/Users/jameschen/.codex/vendor_imports/skills/skills/foo/SKILL.md",
                "root": "codex_vendor",
                "skill_status": "runtime_vendor_readonly",
                "test_level": "quarantine",
                "action": "do_not_claim_as_nexus_skill",
                "capability_mount": None,
                "reason_codes": ["provider_runtime_skill_not_nexus_policy"],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_catalog_allows_only_nexus_curated_runtime_mounts(tmp_path: Path) -> None:
    status_report = tmp_path / "skill_status.json"
    _write_status_report(status_report)

    catalog = SkillCatalog.from_status_report(status_report)

    assert catalog.mount_allowed("nexus-benchmark-public-report") is True
    assert catalog.mount_allowed("candidate-skill-from-run-001") is False
    assert catalog.mount_allowed("hermes-debugging") is False
    assert catalog.ablation_allowed("hermes-debugging") is True
    assert catalog.mount_allowed("create-plan") is False
    assert catalog.ablation_allowed("create-plan") is True
    assert catalog.ablation_allowed("candidate-skill-from-run-001") is False
    assert catalog.mount_allowed("codex-vendor-skill") is False
    assert catalog.mount_allowed("missing") is False


def test_catalog_reports_reference_and_quarantine_violations(tmp_path: Path) -> None:
    status_report = tmp_path / "skill_status.json"
    _write_status_report(status_report)

    catalog = SkillCatalog.from_status_report(status_report)
    violations = catalog.validate_requested_mounts(
        [
            "nexus-benchmark-public-report",
            "candidate-skill-from-run-001",
            "hermes-debugging",
            "create-plan",
            "codex-vendor-skill",
            "missing",
        ]
    )

    assert [v.to_dict() for v in violations] == [
        {
            "skill_name": "candidate-skill-from-run-001",
            "path": "/Users/jameschen/.agents/skills/candidate-skill-from-run-001/SKILL.md",
            "reason": "quarantined_status:candidate_quarantine",
        },
        {
            "skill_name": "hermes-debugging",
            "path": "/Users/jameschen/Workspace/hermes-agent/skills/debugging/SKILL.md",
            "reason": "reference_only_status:external_reference_candidate",
        },
        {
            "skill_name": "create-plan",
            "path": "/repo/.agents/skills/create-plan/SKILL.md",
            "reason": "reference_only_status:nexus_repo_local_candidate",
        },
        {
            "skill_name": "codex-vendor-skill",
            "path": "/Users/jameschen/.codex/vendor_imports/skills/skills/foo/SKILL.md",
            "reason": "quarantined_status:runtime_vendor_readonly",
        },
        {
            "skill_name": "missing",
            "path": "",
            "reason": "skill_not_in_catalog",
        },
    ]


def test_catalog_allows_reference_only_for_ablation_mode(tmp_path: Path) -> None:
    status_report = tmp_path / "skill_status.json"
    _write_status_report(status_report)

    catalog = SkillCatalog.from_status_report(status_report)
    violations = catalog.validate_requested_mounts(
        [
            "nexus-benchmark-public-report",
            "hermes-debugging",
            "candidate-skill-from-run-001",
        ],
        allow_ablation=True,
    )

    assert [v.to_dict() for v in violations] == [
        {
            "skill_name": "candidate-skill-from-run-001",
            "path": "/Users/jameschen/.agents/skills/candidate-skill-from-run-001/SKILL.md",
            "reason": "quarantined_status:candidate_quarantine",
        }
    ]


def test_catalog_builds_mount_contracts_for_runtime_candidates(tmp_path: Path) -> None:
    status_report = tmp_path / "skill_status.json"
    _write_status_report(status_report)

    contracts = SkillCatalog.from_status_report(status_report).mount_contracts()

    assert contracts == [
        {
            "skill_id": "nexus-benchmark-public-report",
            "capability_mount": "benchmark_and_promotion",
            "test_level": "routing_plus_e2e",
            "path": "/repo/.agents/skills/nexus-benchmark-public-report/SKILL.md",
            "evidence_required": [
                "route_reason_codes",
                "skill_id",
                "skill_path",
                "outcome_contribution",
            ],
        }
    ]


def test_catalog_prefers_canonical_runtime_entry_over_worktree_copy(tmp_path: Path) -> None:
    status_report = tmp_path / "skill_status.json"
    _write_status_report(status_report)
    payload = json.loads(status_report.read_text(encoding="utf-8"))
    payload["skills"].append(
        {
            "name": "nexus-benchmark-public-report",
            "path": "/Users/jameschen/.codex/worktrees/demo/.agents/skills/nexus-benchmark-public-report/SKILL.md",
            "root": "codex_worktrees",
            "skill_status": "worktree_copy_quarantine",
            "test_level": "quarantine",
            "action": "do_not_load",
            "capability_mount": None,
            "reason_codes": ["non_canonical_worktree_copy"],
        }
    )
    status_report.write_text(json.dumps(payload), encoding="utf-8")

    catalog = SkillCatalog.from_status_report(status_report)

    assert catalog.mount_allowed("nexus-benchmark-public-report") is True
    assert catalog.validate_requested_mounts(["nexus-benchmark-public-report"]) == []
    assert catalog.get("nexus-benchmark-public-report").path == (
        "/repo/.agents/skills/nexus-benchmark-public-report/SKILL.md"
    )
