from pathlib import Path


def get_new_stale_inventory_rows(repo_root: Path, sources_path: Path) -> list[str]:
    """Audits generated inventory against physical/authoritative repository files."""
    lines = sources_path.read_text(encoding="utf-8").splitlines()
    sources_entries = [
        line.strip() for line in lines if line.strip() and not line.strip().startswith("#")
    ]

    # Compute missing paths
    missing_on_disk = [p for p in sources_entries if not (repo_root / p).exists()]

    # Legacy baseline missing paths (pre-#86 main snapshot)
    legacy_baseline = {
        "nexus-reflex/test_reflex.py",
        "nexus-reflex/python/setup.py",
        "nexus-reflex/python/test_sdk.py",
        "nexus-reflex/python/nexus_reflex/__init__.py",
        "nexus-reflex/python/nexus_reflex/cli.py",
        "scripts/auto_evolution_engine.py",
        "scripts/bootstrap_knowledge.py",
        "scripts/brain_b_health_monitor.py",
        "scripts/brain_b_incubator.py",
        "scripts/brain_dupe_audit.py",
        "scripts/brain_iq_booster.py",
        "scripts/brain_pruner.py",
        "scripts/brain_quality_scorer.py",
        "scripts/brain_search_v3.py",
        "scripts/brain_semantic_audit.py",
        "scripts/brain_synthesizer.py",
        "scripts/conflict_checker.py",
        "scripts/dreaming_engine.py",
        "scripts/drift_detector.py",
        "scripts/evolution_report.py",
        "scripts/flash_ingest.py",
        "scripts/ghost_audit.py",
        "scripts/identity_audit.py",
        "scripts/librarian_ingest_test.py",
        "scripts/link_healer.py",
        "scripts/memory_temp_manager.py",
        "scripts/nexus_v16_5.py",
        "scripts/obsidian_gardener.py",
        "scripts/obsidian_gardener_backup.py",
        "scripts/plot_curve.py",
        "scripts/purge_old_tables.py",
        "scripts/report_search_usage.py",
        "scripts/run_acheron_scan.py",
        "scripts/self_evolution.py",
        "scripts/semantic_gravity_smelter.py",
        "scripts/session_wrap_up.py",
        "scripts/ski_diagnosis.py",
        "scripts/steward.py",
        "scripts/test_distillation_privacy.py",
        "scripts/test_economic_fairness.py",
        "scripts/test_singularity_armor.py",
        "scripts/wisdom_distiller.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_crystallizer_pro.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_dupe_audit.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_iq_booster.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_pruner.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_quality_scorer.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_search_v2.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_semantic_audit.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/brain_synthesizer.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/computer_guard.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/conflict_checker.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/content_agent.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/context_pruner.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/crystallize_via_gws_v3.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/dreaming_engine.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/drift_detector.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/event_logger.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/evolution_report.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/final_path_audit.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/flash_ingest.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/flash_ingest_v2.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/ghost_audit.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/guard_executor.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/idea_check_v2.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/idea_decomposer.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/identity_audit.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/librarian_auditor.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/librarian_ingest.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/link_healer.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/link_mapper.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/memory_temp_manager.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/parallel_spawner.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/path_healer.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/proactive_scout.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/purge_old_tables.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/quality_stamper.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/redundancy_check.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/reflective_healer.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/self_refiner.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/ski_diagnosis.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/skill_generator.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/skill_spec_generator.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/state_reconstructor.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/super_plan_v2.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/task_resumer.py",
        "scripts/_migrated_from_obsidian/01_Operations/scripts/test_crystallize_sync.py",
        "scripts/core/brain_b_health_monitor.py",
        "scripts/core/brain_b_incubator.py",
        "scripts/core/brain_search_v3.py",
        "scripts/core/self_evolution.py",
        "scripts/core/semantic_gravity_smelter.py",
        "scripts/core/steward.py",
    }

    new_stale = [p for p in missing_on_disk if p not in legacy_baseline]
    return new_stale


def test_source_inventory_integrity_current_main():
    repo_root = Path(__file__).resolve().parents[2]
    sources_path = repo_root / "muse_nexus.egg-info" / "SOURCES.txt"

    new_stale = get_new_stale_inventory_rows(repo_root, sources_path)
    assert len(new_stale) == 0, f"Found new stale inventory rows on current main: {new_stale}"


def test_source_inventory_detects_stale_rows(tmp_path: Path):
    fake_sources = tmp_path / "SOURCES.txt"
    fake_sources.write_text("existing.py\nstale_deleted.py\n")

    (tmp_path / "existing.py").write_text("# exists")

    new_stale = get_new_stale_inventory_rows(tmp_path, fake_sources)
    assert "stale_deleted.py" in new_stale
    assert "existing.py" not in new_stale
