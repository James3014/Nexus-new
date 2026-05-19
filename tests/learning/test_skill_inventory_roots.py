import json
from pathlib import Path

from nexus.learning.skill_inventory_roots import (
    apply_cleanup_plan,
    build_canonical_capability_buckets,
    build_cleanup_apply_plan,
    build_full_skill_inventory,
    build_identity_dedup_report,
    build_pairing_identity_recheck,
)


def _skill(path: Path, name: str, description: str = "Use code repair evidence gate.") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n{description}\n",
        encoding="utf-8",
    )


def test_full_inventory_tracks_root_path_sha_identity(tmp_path):
    nexus_root = tmp_path / "Workspace" / "nexus" / ".agents" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    _skill(nexus_root / "tdd", "tdd", "Use TDD repair and test evidence.")
    _skill(codex_root / "tdd", "tdd", "Use TDD repair and test evidence.")

    inventory = build_full_skill_inventory((nexus_root, codex_root))
    dedup = build_identity_dedup_report(inventory)

    assert inventory["summary"]["skill_file_count"] == 2
    assert inventory["summary"]["unique_skill_id_count"] == 1
    assert inventory["summary"]["duplicate_skill_id_count"] == 1
    assert dedup["summary"]["safe_delete_candidate_count"] == 1
    assert dedup["safe_delete_candidates"][0]["source_status"] == "codex_mirror_cache"


def test_sf2_route_fit_specs_are_not_runtime_eligible(tmp_path):
    nexus_root = tmp_path / "Workspace" / "nexus" / ".agents" / "skills"
    _skill(
        nexus_root / "sf2" / "sf2-policy_capability_gate-route-fit-spec",
        "sf2-policy_capability_gate-route-fit-spec",
        "Candidate-only SF route-fit skill for policy_capability_gate.",
    )

    inventory = build_full_skill_inventory((nexus_root,))

    assert inventory["skills"][0]["ablation_eligible"] is True
    assert inventory["skills"][0]["runtime_eligible"] is False


def test_full_inventory_excludes_internal_quarantine(tmp_path):
    nexus_root = tmp_path / "Workspace" / "nexus" / ".agents" / "skills"
    _skill(nexus_root / "tdd", "tdd", "Use TDD repair and test evidence.")
    _skill(nexus_root / ".duplicates-quarantine" / "codex" / "old-tdd", "tdd", "Use TDD repair and test evidence.")

    inventory = build_full_skill_inventory((nexus_root,))

    assert inventory["summary"]["skill_file_count"] == 1
    assert inventory["skills"][0]["relative_dir"] == "tdd"


def test_same_id_different_content_requires_manual_review(tmp_path):
    agents_root = tmp_path / ".agents" / "skills"
    hermes_root = tmp_path / "Workspace" / "hermes-agent" / "skills"
    _skill(agents_root / "research", "research-helper", "Find sources and citations.")
    _skill(hermes_root / "research", "research-helper", "Resolve source conflicts and audit citations.")

    inventory = build_full_skill_inventory((agents_root, hermes_root))
    dedup = build_identity_dedup_report(inventory)

    assert dedup["summary"]["safe_delete_candidate_count"] == 0
    assert dedup["summary"]["manual_review_required_count"] == 1
    assert dedup["manual_review_required"][0]["reason"] == "same_skill_id_different_content"


def test_canonical_buckets_exclude_safe_delete_candidates(tmp_path):
    nexus_root = tmp_path / "Workspace" / "nexus" / ".agents" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    _skill(nexus_root / "tdd", "tdd", "Use TDD repair test receipt evidence.")
    _skill(codex_root / "tdd", "tdd", "Use TDD repair test receipt evidence.")

    inventory = build_full_skill_inventory((nexus_root, codex_root))
    dedup = build_identity_dedup_report(inventory)
    buckets = build_canonical_capability_buckets(inventory, dedup)

    assert buckets["summary"]["canonical_skill_count"] == 1
    assert buckets["summary"]["capability_bucket_count"] == 33
    repair = [
        item
        for item in buckets["capability_buckets"]
        if item["capability_id"] == "repair_loop"
    ][0]
    assert repair["top_candidates"][0]["skill_id"] == "tdd"
    assert repair["top_candidates"][0]["source_status"] == "nexus_repo_local"


def test_pairing_identity_recheck_uses_path_not_skill_id_only(tmp_path):
    nexus_root = tmp_path / "Workspace" / "nexus" / ".agents" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    _skill(nexus_root / "tdd", "tdd", "Use TDD repair test receipt evidence.")
    _skill(codex_root / "tdd", "tdd", "Use TDD repair test receipt evidence.")
    inventory = build_full_skill_inventory((nexus_root, codex_root))
    dedup = build_identity_dedup_report(inventory)

    patch_plan = tmp_path / "patch.json"
    promotion = tmp_path / "promotion.json"
    skill_path = str(nexus_root / "tdd" / "SKILL.md")
    patch_plan.write_text(
        json.dumps(
            {
                "planned_changes": [
                    {
                        "capability_id": "repair_loop",
                        "skill_id": "tdd",
                        "skill_path": skill_path,
                        "planned_action": "RUNTIME_DEFAULT_REVIEW",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    promotion.write_text(json.dumps({"review_items": []}), encoding="utf-8")

    recheck = build_pairing_identity_recheck(
        patch_plan_path=patch_plan,
        promotion_review_path=promotion,
        inventory=inventory,
        dedup_report=dedup,
    )

    assert recheck["status"] == "PASS"
    assert recheck["summary"]["warning_count"] == 1
    assert recheck["pairings"][0]["source_status"] == "nexus_repo_local"


def test_cleanup_apply_plan_quarantines_only_safe_duplicates(tmp_path):
    nexus_root = tmp_path / "Workspace" / "nexus" / ".agents" / "skills"
    codex_root = tmp_path / ".codex" / "skills"
    _skill(nexus_root / "tdd", "tdd", "Use TDD repair test receipt evidence.")
    _skill(codex_root / "tdd", "tdd", "Use TDD repair test receipt evidence.")
    inventory = build_full_skill_inventory((nexus_root, codex_root))
    dedup = build_identity_dedup_report(inventory)
    plan = build_cleanup_apply_plan(
        inventory=inventory,
        dedup_report=dedup,
        quarantine_root=tmp_path / "quarantine",
    )
    dry_run = apply_cleanup_plan(plan, mode="dry-run")
    applied = apply_cleanup_plan(plan, mode="quarantine")

    assert plan["summary"]["planned_quarantine_count"] == 1
    assert dry_run["summary"]["status_counts"] == {"WOULD_MOVE": 1}
    assert applied["summary"]["status_counts"] == {"MOVED": 1}
    assert not (codex_root / "tdd").exists()
    assert (nexus_root / "tdd" / "SKILL.md").exists()
