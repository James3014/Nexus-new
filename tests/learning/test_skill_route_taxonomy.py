import json
from pathlib import Path

from scripts.ops.materialize_sf2_candidate_assets import verify_materialized_assets

from nexus.learning.sf2_bounded_probe import (
    build_sf2_completion_gate,
    build_sf2_live_receipt_validation,
    build_sf2_probe_verdict_catalog,
    build_sf2_promotion_review,
    build_sf3_best_candidate_search,
    build_sf3_candidate_only_hardening_plan,
    build_sf3_candidate_metadata_overlay,
    build_sf3_evidence_based_approval_artifact,
    build_sf3_combo_probe,
    build_sf3_live_causality_probe,
    build_sf3_manual_approval_packet,
    build_sf3_manual_approval_validation,
    build_sf3_manual_runtime_policy_review,
    build_sf3_metadata_bias_rescue,
    build_sf3_capability_overlap_resolver,
    build_sf3_post_review_gate,
    build_sf3_runtime_policy_apply_gate,
    build_sf3_runtime_policy_approval_draft,
    build_sf3_runtime_policy_patch_plan,
    build_sf3_runtime_review_gate,
    run_sf2_probe_chunk,
)
from nexus.learning.skill_route_taxonomy import (
    build_sf2_ablation_matrix_plan,
    build_sf2_candidate_materialization_bundle,
    build_sf2_candidate_spec_overlay,
    build_sf2_candidate_quality_screen,
    build_sf2_closure_gate,
    build_sf2_bounded_probe_plan,
    build_sf2_bounded_probe_preflight,
    build_sf2_bounded_probe_task_manifest,
    build_sf2_bounded_probe_execution_manifest,
    build_sf2_bounded_probe_chunk_plan,
    build_sf2_materialization_batch_plan,
    build_route_capability_taxonomy,
    build_sf2_capability_candidate_selection,
    build_sf2_metadata_repair_plan,
    build_sf2_spec_repaired_candidate_pool,
    build_skill_route_reclassification,
    classify_skill_for_route_capabilities,
    write_json_report,
)


def test_taxonomy_covers_new_route_core_capabilities():
    taxonomy = build_route_capability_taxonomy()
    capability_ids = {item["capability_id"] for item in taxonomy["capabilities"]}

    assert taxonomy["status"] == "PASS"
    assert "codeintel" in capability_ids
    assert "autoreason" in capability_ids
    assert "ddtree" in capability_ids
    assert "mempalace" in capability_ids
    assert "artifact_gate" in capability_ids
    assert "claim_gate" in capability_ids
    assert "swarm_multi_agent" in capability_ids
    assert "drone" in capability_ids
    assert "benchmark_meta_opt" in capability_ids


def test_reclassification_maps_legacy_and_keyword_capabilities():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "candidates": [
            {
                "skill_id": "tdd",
                "path": "/repo/.agents/skills/tdd/SKILL.md",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "safety_status": "runtime_reviewed",
                "ablation_eligible": True,
                "runtime_eligible": True,
                "capability_candidates": ["repair_and_coding"],
                "load_when": "Use test-driven repair and refactor loops.",
            },
            {
                "skill_id": "source-validator",
                "path": "/repo/.agents/skills/source-validator/SKILL.md",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "safety_status": "ablation_only",
                "ablation_eligible": True,
                "runtime_eligible": False,
                "capability_candidates": [],
                "load_when": "Validate citation chain and source conflict evidence.",
            },
        ],
    }

    report = build_skill_route_reclassification(pool)
    by_id = {item["skill_id"]: item for item in report["skills"]}
    tdd_caps = {item["capability_id"] for item in by_id["tdd"]["route_capability_candidates"]}
    research_caps = {item["capability_id"] for item in by_id["source-validator"]["route_capability_candidates"]}

    assert report["status"] == "PASS"
    assert "repair_loop" in tdd_caps
    assert "research_control_plane" in research_caps
    assert report["summary"]["classified_skill_count"] == 2


def test_reclassification_uses_capability_id_exact_match_for_route_fit_specs():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "candidates": [
            {
                "skill_id": "sf2-learning_closure-route-fit-spec",
                "path": "/repo/.agents/skills/sf2/sf2-learning_closure-route-fit-spec/SKILL.md",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "safety_status": "ablation_only",
                "ablation_eligible": True,
                "runtime_eligible": False,
                "capability_candidates": [],
                "load_when": "Candidate-only route-fit skill for learning_closure.",
            }
        ],
    }

    report = build_skill_route_reclassification(pool)
    by_id = {item["skill_id"]: item for item in report["skills"]}
    caps = {item["capability_id"]: item for item in by_id["sf2-learning_closure-route-fit-spec"]["route_capability_candidates"]}

    assert "learning_closure" in caps
    assert caps["learning_closure"]["confidence"] == "high"
    assert "capability_id_match:learning_closure" in caps["learning_closure"]["reasons"]


def test_candidate_selection_produces_capability_local_shortlists():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "candidates": [
            {
                "skill_id": "codeintel-scan",
                "path": "/repo/.agents/skills/codeintel-scan/SKILL.md",
                "source_root": "nexus_repo",
                "source_type": "nexus_local",
                "safety_status": "runtime_reviewed",
                "ablation_eligible": True,
                "runtime_eligible": True,
                "capability_candidates": [],
                "load_when": "Run code scan and impact graph.",
            },
            {
                "skill_id": "quarantined-codeintel",
                "path": "/tmp/worktree/codeintel/SKILL.md",
                "source_root": "codex_worktrees",
                "source_type": "quarantine",
                "safety_status": "quarantined",
                "ablation_eligible": False,
                "runtime_eligible": False,
                "capability_candidates": [],
                "load_when": "codeintel scan",
            },
        ],
    }

    reclassification = build_skill_route_reclassification(pool)
    selection = build_sf2_capability_candidate_selection(reclassification, max_candidates_per_capability=4)
    by_capability = {item["capability_id"]: item for item in selection["selections"]}

    assert by_capability["codeintel"]["candidate_count"] == 1
    assert by_capability["codeintel"]["candidates"][0]["skill_id"] == "codeintel-scan"
    assert all(
        candidate["skill_id"] != "quarantined-codeintel"
        for item in selection["selections"]
        for candidate in item["candidates"]
    )


def test_candidate_selection_surfaces_metadata_repair_candidates():
    pool = {
        "schema": "nexus.fair_skill_candidate_pool.v1",
        "candidates": [
            {
                "skill_id": "agent-longrun-task-tracker",
                "path": "/Users/jameschen/.agents/skills/devops/agent-longrun-task-tracker/SKILL.md",
                "source_root": "agents",
                "source_type": "local_candidate",
                "safety_status": "ablation_only",
                "ablation_eligible": False,
                "runtime_eligible": False,
                "capability_candidates": [],
                "load_when": "Track longrun nightshift recovery tasks.",
            },
        ],
    }

    reclassification = build_skill_route_reclassification(pool)
    selection = build_sf2_capability_candidate_selection(reclassification, max_candidates_per_capability=4)
    by_capability = {item["capability_id"]: item for item in selection["selections"]}

    assert by_capability["nightshift"]["candidate_count"] == 0
    assert by_capability["nightshift"]["metadata_repair_candidate_count"] == 1
    assert by_capability["nightshift"]["next_action"] == "metadata_repair_required"
    assert selection["summary"]["capabilities_with_metadata_repair_candidates"] >= 1


def test_metadata_repair_plan_does_not_allow_runtime_update():
    selection = {
        "selections": [
            {
                "capability_id": "nightshift",
                "candidate_count": 0,
                "metadata_repair_candidate_count": 1,
                "metadata_repair_candidates": [
                    {
                        "skill_id": "agent-longrun-task-tracker",
                        "path": "/repo/agent-longrun-task-tracker/SKILL.md",
                        "source_root": "agents",
                        "source_type": "reference",
                        "safety_status": "ablation_only",
                        "metadata_quality": "INCOMPLETE:capability_mount",
                    }
                ],
            }
        ]
    }

    plan = build_sf2_metadata_repair_plan(selection)

    assert plan["status"] == "PASS"
    assert plan["summary"]["repair_item_count"] == 1
    assert plan["summary"]["runtime_update_allowed"] is False
    assert plan["repair_items"][0]["proposed_capability_mount"] == "reference:nightshift"
    assert plan["repair_items"][0]["post_repair_ablation_eligible"] is True
    assert plan["repair_items"][0]["post_repair_runtime_eligible"] is False


def test_ablation_matrix_plan_blocks_metadata_repair_capability_and_keeps_negative_controls():
    selection = {
        "selections": [
            {
                "capability_id": "repair_loop",
                "candidate_count": 1,
                "candidates": [
                    {
                        "skill_id": "tdd",
                        "runtime_eligible": True,
                        "ablation_eligible": True,
                        "safety_status": "runtime_reviewed",
                    }
                ],
                "metadata_repair_candidate_count": 0,
                "metadata_repair_candidates": [],
            },
            {
                "capability_id": "nightshift",
                "candidate_count": 0,
                "candidates": [],
                "metadata_repair_candidate_count": 1,
                "metadata_repair_candidates": [{"skill_id": "agent-longrun-task-tracker"}],
            },
        ]
    }

    plan = build_sf2_ablation_matrix_plan(selection)
    by_capability = {item["capability_id"]: item for item in plan["plans"]}

    assert plan["status"] == "PARTIAL"
    assert plan["summary"]["ready_capability_count"] == 1
    assert plan["summary"]["blocked_capability_count"] == 1
    assert by_capability["repair_loop"]["status"] == "READY"
    assert by_capability["nightshift"]["reason"] == "metadata_repair_required"
    assert any(row["arm_type"] == "negative_control" for row in by_capability["repair_loop"]["rows"])


def test_ablation_matrix_plan_can_apply_metadata_repair_overlay_without_runtime_update():
    selection = {
        "selections": [
            {
                "capability_id": "nightshift",
                "candidate_count": 0,
                "candidates": [],
                "metadata_repair_candidate_count": 1,
                "metadata_repair_candidates": [
                    {
                        "skill_id": "agent-longrun-task-tracker",
                        "runtime_eligible": False,
                        "ablation_eligible": False,
                        "safety_status": "ablation_only",
                    }
                ],
            },
        ]
    }

    plan = build_sf2_ablation_matrix_plan(selection, allow_metadata_repair_overlay=True)
    rows = plan["plans"][0]["rows"]
    skill_rows = [row for row in rows if row["arm_type"] == "skill_arm"]

    assert plan["status"] == "PASS"
    assert plan["summary"]["blocked_capability_count"] == 0
    assert plan["summary"]["metadata_repair_overlay_row_count"] == 1
    assert plan["summary"]["runtime_update_allowed"] is False
    assert skill_rows[0]["metadata_repaired_overlay"] is True
    assert skill_rows[0]["runtime_eligible"] is False
    assert skill_rows[0]["ablation_eligible"] is True


def test_candidate_quality_screen_blocks_weak_route_fit_before_live_probe():
    reclassification = {
        "skills": [
            {
                "skill_id": "opaque",
                "ablation_eligible": True,
                "runtime_eligible": False,
                "route_capability_candidates": [
                    {
                        "capability_id": "external_productivity",
                        "confidence": "low",
                        "score": 0,
                        "reasons": ["fallback:no_route_keyword_match"],
                    }
                ],
            }
        ]
    }
    selection = {
        "selections": [
            {
                "capability_id": "external_productivity",
                "candidate_count": 1,
                "candidates": [{"skill_id": "opaque", "ablation_eligible": True, "runtime_eligible": False}],
            }
        ]
    }

    screen = build_sf2_candidate_quality_screen(reclassification, selection)

    assert screen["status"] == "REVIEW_REQUIRED"
    assert screen["summary"]["sf2_live_probe_allowed"] is False
    assert screen["candidates"][0]["review_reasons"] == [
        "weak_match_confidence:low",
        "weak_match_score:0",
        "insufficient_route_keyword_score:0",
    ]


def test_candidate_spec_overlay_repairs_blocked_capability_without_runtime_update():
    quality_screen = {
        "blocked_shortlists": [
            {
                "capability_id": "autonomic_router",
                "required_behavior": "autonomic route selection",
                "required_route_terms": ["autonomic", "router"],
            }
        ]
    }
    base_pool = {"schema": "example", "candidates": []}

    overlay = build_sf2_candidate_spec_overlay(quality_screen)
    repaired_pool = build_sf2_spec_repaired_candidate_pool(base_pool, overlay)
    reclassification = build_skill_route_reclassification(repaired_pool)
    selection = build_sf2_capability_candidate_selection(reclassification)
    screen = build_sf2_candidate_quality_screen(reclassification, selection)
    clean_by_capability = {item["capability_id"]: item for item in screen["clean_shortlists"]}

    assert overlay["summary"]["spec_candidate_count"] == 1
    assert repaired_pool["summary"]["runtime_update_allowed"] is False
    assert clean_by_capability["autonomic_router"]["candidate_count"] == 1
    assert clean_by_capability["autonomic_router"]["candidates"][0]["runtime_eligible"] is False


def test_spec_overlay_candidate_is_not_crowded_out_by_legacy_candidates():
    capability = "forecast_pregate"
    base_candidates = [
        {
            "skill_id": f"legacy-plan-{index}",
            "source_root": "nexus_repo",
            "source_type": "nexus_local",
            "safety_status": "runtime_reviewed",
            "ablation_eligible": True,
            "runtime_eligible": True,
            "metadata_quality": "PASS",
            "capability_candidates": ["planning_and_handoff"],
            "load_when": "Plan handoff.",
        }
        for index in range(10)
    ]
    base_pool = {"schema": "example", "candidates": base_candidates}
    overlay = build_sf2_candidate_spec_overlay({"blocked_shortlists": [{"capability_id": capability}]})
    repaired_pool = build_sf2_spec_repaired_candidate_pool(base_pool, overlay)
    reclassification = build_skill_route_reclassification(repaired_pool)
    selection = build_sf2_capability_candidate_selection(reclassification, max_candidates_per_capability=8)
    by_capability = {item["capability_id"]: item for item in selection["selections"]}

    assert by_capability[capability]["candidates"][0]["skill_id"] == f"sf2-{capability}-route-fit-spec"


def test_candidate_materialization_bundle_keeps_assets_candidate_only():
    overlay = build_sf2_candidate_spec_overlay({"blocked_shortlists": [{"capability_id": "belief"}]})

    bundle = build_sf2_candidate_materialization_bundle(overlay)
    asset = bundle["assets"][0]

    assert bundle["status"] == "PASS"
    assert bundle["summary"]["asset_count"] == 1
    assert bundle["summary"]["runtime_update_allowed"] is False
    assert asset["target_path"] == ".agents/skills/sf2/sf2-belief-route-fit-spec/SKILL.md"
    assert asset["node_layer"] == "agent_extending"
    assert asset["retry_policy"]["budget_safety_floor_preserved"] is True
    assert asset["context_policy"]["requires_context_compactor_when_cnr_gt"] == 0.6
    assert "prompt_hashes" in asset["evidence_outputs_required"]
    assert "runtime_eligible: false" in asset["skill_md"]
    assert "candidate-only" in asset["skill_md"]


def test_sf2_closure_gate_allows_only_bounded_probe_when_inputs_ready():
    gate = build_sf2_closure_gate(
        {"summary": {"sf2_live_probe_allowed": True}},
        {"summary": {"ready_capability_count": 33, "capability_count": 33}},
        {"summary": {"ready_to_write_candidate_assets": True}},
    )

    assert gate["status"] == "PASS"
    assert gate["summary"]["bounded_probe_allowed"] is True
    assert gate["summary"]["runtime_update_allowed"] is False
    assert gate["summary"]["public_benchmark_allowed"] is False


def test_materialization_batch_plan_splits_candidate_asset_writes():
    overlay = {
        "spec_candidates": [
            {
                "skill_id": f"sf2-{capability_id}-route-fit-spec",
                "load_when": f"Use when route capability is {capability_id}.",
                "sf2_overlay": {"capability_id": capability_id},
            }
            for capability_id in ("belief", "memory", "mempalace")
        ]
    }
    bundle = build_sf2_candidate_materialization_bundle(overlay)
    plan = build_sf2_materialization_batch_plan(bundle, max_assets_per_batch=2)

    assert plan["status"] == "PASS"
    assert plan["summary"]["asset_count"] == 3
    assert plan["summary"]["batch_count"] == 2
    assert plan["batches"][0]["batch_id"] == "SF2-H1"
    assert plan["batches"][0]["asset_count"] == 2
    assert plan["batches"][1]["batch_id"] == "SF2-H2"
    assert plan["batches"][1]["asset_count"] == 1
    assert plan["summary"]["runtime_update_allowed"] is False


def test_verify_materialized_assets_requires_candidate_only_boundaries(tmp_path, monkeypatch):
    project_root = tmp_path / "repo"
    target = project_root / ".agents/skills/sf2/demo/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "---\n"
        "metadata:\n"
        "  runtime_eligible: false\n"
        "  public_benchmark_allowed: false\n"
        "---\n"
        "This asset is candidate-only.\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "skill_id": "demo",
                        "target_path": ".agents/skills/sf2/demo/SKILL.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.ops.materialize_sf2_candidate_assets.PROJECT_ROOT", project_root)

    status = verify_materialized_assets(bundle)

    assert status["status"] == "PASS"
    assert status["summary"]["status_visible_asset_count"] == 1
    assert status["summary"]["bounded_probe_allowed"] is True
    assert status["summary"]["runtime_update_allowed"] is False


def test_bounded_probe_plan_requires_ready_matrix_and_visible_assets():
    matrix = {
        "summary": {"capability_count": 1, "ready_capability_count": 1, "planned_row_count": 3},
        "plans": [
            {
                "capability_id": "belief",
                "status": "READY",
                "rows": [
                    {"arm_type": "capability_only"},
                    {"arm_type": "skill_arm"},
                    {"arm_type": "negative_control"},
                ],
            }
        ],
    }
    asset_status = {
        "summary": {
            "asset_count": 1,
            "status_visible_asset_count": 1,
        }
    }

    plan = build_sf2_bounded_probe_plan(matrix, asset_status)

    assert plan["status"] == "PASS"
    assert plan["summary"]["bounded_probe_allowed"] is True
    assert plan["summary"]["runtime_update_allowed"] is False
    assert plan["summary"]["public_benchmark_allowed"] is False
    assert plan["capabilities"][0]["capability_only_count"] == 1
    assert plan["capabilities"][0]["skill_arm_count"] == 1
    assert plan["capabilities"][0]["negative_control_count"] == 1


def test_bounded_probe_preflight_requires_visible_sf2_skill_assets():
    matrix = {
        "plans": [
            {
                "capability_id": "belief",
                "status": "READY",
                "rows": [
                    {"row_id": "belief::capability_only", "arm_type": "capability_only"},
                    {
                        "row_id": "belief::skill_arm_001::sf2-belief-route-fit-spec",
                        "arm_type": "skill_arm",
                        "skill_id": "sf2-belief-route-fit-spec",
                        "ablation_eligible": True,
                    },
                    {"row_id": "belief::negative_control", "arm_type": "negative_control"},
                ],
            }
        ]
    }
    asset_status = {
        "assets": [
            {
                "skill_id": "sf2-belief-route-fit-spec",
                "status": "PASS",
            }
        ]
    }

    preflight = build_sf2_bounded_probe_preflight(matrix, asset_status)

    assert preflight["status"] == "PASS"
    assert preflight["summary"]["row_count"] == 3
    assert preflight["summary"]["bounded_probe_live_allowed"] is True
    assert preflight["summary"]["outcome_contribution_claimed"] is False


def test_bounded_probe_execution_manifest_attaches_tasks_without_public_benchmark():
    taxonomy = {"capabilities": [{"capability_id": "belief", "group": "reasoning", "pillar": "belief", "phases": ["P"]}]}
    matrix = {
        "plans": [
            {
                "capability_id": "belief",
                "status": "READY",
                "rows": [
                    {"row_id": "belief::capability_only", "capability_id": "belief", "arm_type": "capability_only"},
                    {
                        "row_id": "belief::skill_arm_001::sf2-belief-route-fit-spec",
                        "capability_id": "belief",
                        "arm_type": "skill_arm",
                        "skill_id": "sf2-belief-route-fit-spec",
                    },
                ],
            }
        ]
    }

    task_manifest = build_sf2_bounded_probe_task_manifest(taxonomy)
    execution = build_sf2_bounded_probe_execution_manifest(matrix, task_manifest)

    assert task_manifest["summary"]["task_count"] == 1
    assert task_manifest["tasks"][0]["id"] == "sf2-route-fit-belief-001"
    assert task_manifest["tasks"][0]["repo_kind"] == "neutral_fixture"
    assert execution["status"] == "PASS"
    assert execution["summary"]["row_count"] == 2
    assert execution["summary"]["ready_for_sf2_live_probe"] is True
    assert execution["rows"][0]["task_ref"]["task_id"] == "sf2-route-fit-belief-001"
    assert execution["rows"][1]["runner_args"][:3] == ["uv", "run", "python"]
    assert execution["rows"][1]["runner_env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"] == "sf2-belief-route-fit-spec"
    assert execution["summary"]["public_benchmark_allowed"] is False


def test_bounded_probe_chunk_plan_splits_execution_rows_without_benchmark_claims():
    execution = {
        "rows": [
            {"row_id": "belief::capability_only", "capability_id": "belief"},
            {"row_id": "belief::skill_arm_001", "capability_id": "belief"},
            {"row_id": "claim_gate::capability_only", "capability_id": "claim_gate"},
            {"row_id": "claim_gate::skill_arm_001", "capability_id": "claim_gate"},
            {"row_id": "claim_gate::negative_control", "capability_id": "claim_gate"},
        ]
    }

    plan = build_sf2_bounded_probe_chunk_plan(execution, max_rows_per_chunk=2)

    assert plan["status"] == "PASS"
    assert plan["summary"]["row_count"] == 5
    assert plan["summary"]["chunk_count"] == 3
    assert plan["summary"]["runtime_update_allowed"] is False
    assert plan["summary"]["public_benchmark_allowed"] is False
    assert plan["chunks"][0]["chunk_id"] == "SF2-I3-01"
    assert plan["chunks"][0]["row_count"] == 2
    assert plan["chunks"][2]["row_ids"] == ["claim_gate::negative_control"]


def test_sf2_bounded_probe_static_receipts_keep_runtime_and_benchmark_blocked(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "sf2" / "sf2-belief-route-fit-spec"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "belief route fit evidence receipt gate outcome contract",
        encoding="utf-8",
    )
    execution = {
        "rows": [
            {
                "row_id": "belief::capability_only",
                "capability_id": "belief",
                "arm_type": "capability_only",
                "task_ref": {"task_id": "sf2-route-fit-belief-001"},
            },
            {
                "row_id": "belief::skill_arm_001::sf2-belief-route-fit-spec",
                "capability_id": "belief",
                "arm_type": "skill_arm",
                "skill_id": "sf2-belief-route-fit-spec",
                "task_ref": {"task_id": "sf2-route-fit-belief-001"},
            },
            {
                "row_id": "belief::negative_control",
                "capability_id": "belief",
                "arm_type": "negative_control",
                "task_ref": {"task_id": "sf2-route-fit-belief-001"},
            },
        ]
    }
    tasks = {"tasks": [{"id": "sf2-route-fit-belief-001", "capability_id": "belief", "task_desc": "belief route fit"}]}
    chunk = {"chunk_id": "SF2-I3-01", "row_ids": [row["row_id"] for row in execution["rows"]]}

    report = run_sf2_probe_chunk(execution_manifest=execution, task_manifest=tasks, chunk=chunk, repo_root=tmp_path)
    catalog = build_sf2_probe_verdict_catalog([report])

    assert report["status"] == "PASS"
    assert report["summary"]["public_benchmark_allowed"] is False
    assert catalog["status"] == "PASS"
    assert catalog["summary"]["runtime_update_allowed"] is False
    assert catalog["capabilities"][0]["candidates"][0]["verdict"] == "static_fit_candidate"


def test_sf2_completion_gate_closes_only_after_receipts_and_dispositions(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "sf2" / "sf2-belief-route-fit-spec"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text("belief evidence receipt gate outcome", encoding="utf-8")
    catalog = {
        "schema": "nexus.sf2_final_route_skill_verdict_catalog.v1",
        "status": "PASS",
        "summary": {"blocked_capability_count": 0, "sf_discovery_closed": True},
        "capabilities": [
            {
                "capability_id": "belief",
                "static_fit_candidate_count": 1,
                "candidates": [
                    {
                        "skill_id": "sf2-belief-route-fit-spec",
                        "verdict": "static_fit_candidate",
                        "skill_path": str(skill_path),
                        "route_overlap": ["belief"],
                        "evidence_overlap": ["evidence", "receipt"],
                    }
                ],
            }
        ],
    }

    receipts = build_sf2_live_receipt_validation(catalog)
    review = build_sf2_promotion_review(receipts)
    gate = build_sf2_completion_gate(catalog, receipts, review)

    assert receipts["status"] == "PASS"
    assert review["status"] == "PASS"
    assert review["summary"]["candidate_only_catalog_alternate_count"] == 1
    assert gate["status"] == "PASS"
    assert gate["summary"]["sf2_closed_loop_complete"] is True
    assert gate["summary"]["runtime_update_allowed"] is False


def test_sf3_gates_close_live_combo_best_candidate_without_runtime_updates():
    receipts = {
        "capabilities": [
            {
                "capability_id": capability_id,
                "candidates": [
                    {
                        "skill_id": f"{capability_id}-skill",
                        "receipt_status": "PASS",
                        "skill_path": f"/repo/.agents/skills/{capability_id}-skill/SKILL.md",
                    }
                ],
            }
            for capability_id in [
                "codeintel",
                "repair_loop",
                "artifact_gate",
                "research",
                "lancedb",
                "claim_gate",
                "mempalace",
                "policy_capability_gate",
                "ultra_review",
                "swarm_multi_agent",
                "drone",
                "file_lock_security_gate",
            ]
        ]
    }
    review = {
        "review_items": [
            {
                "capability_id": capability["capability_id"],
                "skill_id": capability["candidates"][0]["skill_id"],
                "disposition": "runtime_review_required",
            }
            for capability in receipts["capabilities"]
        ]
    }

    live = build_sf3_live_causality_probe(receipts)
    combo = build_sf3_combo_probe(live)
    overlap = build_sf3_capability_overlap_resolver(live)
    rescue = build_sf3_metadata_bias_rescue(review)
    best = build_sf3_best_candidate_search(live, review, combo, overlap)
    gate = build_sf3_runtime_review_gate(live, combo, best)

    assert live["status"] == "PASS"
    assert live["capabilities"][0]["candidates"][0]["baseline_vs_skill_delta"]["verified_delta"]
    assert combo["status"] == "PASS"
    assert combo["combos"][0]["arm_type"] == "combo_arm"
    assert combo["combos"][0]["multi_skill_mounts"]
    assert overlap["status"] == "PASS"
    assert "canonical_candidate_id" in overlap["overlaps"][0]
    assert rescue["status"] == "PASS"
    assert best["status"] == "PASS"
    assert best["capabilities"][0]["default_candidate"]["score_components"]["live_outcome"] == 5
    assert gate["status"] == "PASS"
    assert gate["summary"]["sf3_closed_loop_complete"] is True
    assert gate["summary"]["runtime_update_allowed"] is False


def test_sf3_post_review_gate_closes_without_runtime_or_benchmark_unlock():
    runtime_gate = {
        "status": "PASS",
        "summary": {
            "sf3_closed_loop_complete": True,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
    }
    best = {
        "capabilities": [
            {
                "capability_id": "codeintel",
                "default_candidate": {
                    "skill_id": "codeintel-skill",
                    "score": 15,
                    "score_components": {"live_outcome": 5},
                    "disposition": "runtime_review_required",
                    "recommendation": "default_candidate",
                },
                "alternates": [],
            }
        ]
    }
    rescue = {
        "rescued_candidates": [
            {
                "capability_id": "research",
                "skill_id": "candidate-only-source-skill",
                "required_metadata": ["load_when", "expected_evidence"],
            }
        ]
    }

    manual_review = build_sf3_manual_runtime_policy_review(runtime_gate, best)
    hardening = build_sf3_candidate_only_hardening_plan(rescue, max_files_per_batch=15)
    post_review = build_sf3_post_review_gate(runtime_gate, manual_review, hardening)

    assert manual_review["status"] == "PASS"
    assert manual_review["summary"]["runtime_review_ready"] is True
    assert manual_review["review_items"][0]["runtime_policy_action"] == "PROPOSE_ONLY"
    assert hardening["status"] == "PASS"
    assert hardening["summary"]["max_files_per_batch"] == 15
    assert hardening["batches"][0]["item_count"] == 1
    assert post_review["status"] == "PASS"
    assert post_review["summary"]["sf_closed_loop_complete"] is True
    assert post_review["summary"]["sf_state"] == "PROMOTION_REVIEW_READY"
    assert post_review["summary"]["runtime_update_allowed"] is False
    assert post_review["summary"]["public_benchmark_allowed"] is False


def test_sf3_policy_approval_draft_keeps_runtime_apply_blocked_until_manual_approval():
    manual_review = {
        "status": "PASS",
        "review_items": [
            {
                "capability_id": "research",
                "skill_id": "candidate-only-source-skill",
                "source_disposition": "candidate_only_catalog_alternate",
            },
            {
                "capability_id": "codeintel",
                "skill_id": "runtime-reviewed-skill",
                "source_disposition": "runtime_review_required",
            },
        ],
    }
    hardening = {
        "batches": [
            {
                "batch_id": "SF3-HARDEN-01",
                "items": [
                    {
                        "capability_id": "research",
                        "skill_id": "candidate-only-source-skill",
                    }
                ],
            }
        ]
    }

    overlay = build_sf3_candidate_metadata_overlay(hardening)
    draft = build_sf3_runtime_policy_approval_draft(manual_review, overlay)
    apply_gate = build_sf3_runtime_policy_apply_gate(draft)
    packet = build_sf3_manual_approval_packet(draft, overlay)
    evidence_approval = build_sf3_evidence_based_approval_artifact(packet)

    assert overlay["status"] == "PASS"
    assert overlay["summary"]["overlay_count"] == 1
    assert draft["status"] == "PASS"
    assert draft["summary"]["approval_item_count"] == 2
    assert draft["summary"]["pending_manual_approval_count"] == 2
    assert draft["summary"]["metadata_overlay_missing_count"] == 0
    assert apply_gate["status"] == "BLOCKED"
    assert apply_gate["summary"]["runtime_policy_apply_allowed"] is False
    assert apply_gate["blockers"] == ["pending_manual_approval"]
    assert packet["status"] == "PASS"
    assert packet["summary"]["packet_item_count"] == 2
    assert packet["summary"]["runtime_review_recommendation_count"] == 1
    assert packet["summary"]["alternate_recommendation_count"] == 1
    assert packet["packet_items"][0]["risk_flags"] == ["candidate_only_requires_curated_review"]
    assert evidence_approval["status"] == "PASS"
    assert evidence_approval["summary"]["runtime_review_decision_count"] == 1
    assert evidence_approval["summary"]["alternate_decision_count"] == 1
    assert evidence_approval["approval_items"][0]["decision"] == "APPROVE_AS_ALTERNATE"


def test_sf3_manual_approval_validation_blocks_missing_and_unsafe_decisions():
    packet = {
        "packet_items": [
            {
                "capability_id": "research",
                "skill_id": "candidate-only-source-skill",
                "default_review_decision": "APPROVE_AS_ALTERNATE",
                "risk_flags": ["candidate_only_requires_curated_review"],
            },
            {
                "capability_id": "codeintel",
                "skill_id": "runtime-reviewed-skill",
                "default_review_decision": "APPROVE_FOR_RUNTIME_REVIEW",
                "risk_flags": [],
            },
        ]
    }
    unsafe_artifact = {
        "approval_items": [
            {
                "capability_id": "research",
                "skill_id": "candidate-only-source-skill",
                "decision": "APPROVE_FOR_RUNTIME_REVIEW",
            }
        ]
    }

    unsafe = build_sf3_manual_approval_validation(packet, unsafe_artifact)
    safe = build_sf3_manual_approval_validation(
        packet,
        build_sf3_evidence_based_approval_artifact(packet),
    )

    assert unsafe["status"] == "BLOCKED"
    assert any("candidate_only_cannot_skip_curated_review" in item for item in unsafe["blockers"])
    assert any("missing_decision" in item for item in unsafe["blockers"])
    assert safe["status"] == "PASS"
    assert safe["summary"]["valid_decision_count"] == 2
    assert safe["summary"]["runtime_update_allowed"] is False

    blocked_plan = build_sf3_runtime_policy_patch_plan(unsafe)
    patch_plan = build_sf3_runtime_policy_patch_plan(safe)
    final_apply_gate = build_sf3_runtime_policy_apply_gate(patch_plan)

    assert blocked_plan["status"] == "BLOCKED"
    assert blocked_plan["blockers"] == ["approval_validation_not_pass"]
    assert patch_plan["status"] == "PASS"
    assert patch_plan["summary"]["planned_change_count"] == 2
    assert patch_plan["summary"]["runtime_default_review_count"] == 1
    assert patch_plan["summary"]["catalog_alternate_only_count"] == 1
    assert patch_plan["summary"]["public_benchmark_allowed"] is False
    assert final_apply_gate["status"] == "PASS"
    assert final_apply_gate["summary"]["runtime_policy_apply_allowed"] is True
    assert final_apply_gate["summary"]["public_benchmark_allowed"] is False


def test_write_json_report_outputs_json(tmp_path: Path):
    output = tmp_path / "report.json"
    report = write_json_report({"schema": "example", "status": "PASS"}, output)

    assert report["status"] == "PASS"
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == "example"


def test_unmatched_skill_gets_low_confidence_fallback_classification():
    result = classify_skill_for_route_capabilities({"skill_id": "opaque", "load_when": "miscellaneous helper"})

    assert result[0]["capability_id"] == "external_productivity"
    assert result[0]["confidence"] == "low"
