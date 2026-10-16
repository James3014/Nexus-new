# Archive manifest: tests, 2026-10

Archived tests of archived scripts. tests/archive is in pytest.ini norecursedirs; pure git mv, nothing deleted. Files carry a .txt suffix (test_x.py -> test_x.py.txt): the impact gate runs every changed test_*.py by explicit path (which bypasses norecursedirs and --ignore), and an archived test cannot import its moved script, so a .py file would fail on the head side. To resurrect one, drop the .txt and move its script back.

## Batch 2 (tests of archived scripts)

Evidence: ~/Workspace/nexus-handoffs/2026-10-13-online-ab/ARCHIVE_CLASSIFICATION_20261016.md (batch 2) re-derived on main c48689bb4 by whole-repo basename/path scans; each script moves only together with every test that imports it. Pre-move ref: archive/2026-10-17-batch-2-pre.

Files: 43

| original path | new path | class | last commit |
|---|---|---|---|
| tests/bench/test_eia_roi_wave2.py | tests/archive/2026-10/bench/test_eia_roi_wave2.py | test of archived script | 2026-08-23 |
| tests/bench/test_eia_roi_wave2_physical.py | tests/archive/2026-10/bench/test_eia_roi_wave2_physical.py | test of archived script | 2026-08-23 |
| tests/bench/test_legacy_report_output_policy.py | tests/archive/2026-10/bench/test_legacy_report_output_policy.py | test of archived script | 2026-07-14 |
| tests/bench/test_n30r_heldout_task_bank.py | tests/archive/2026-10/bench/test_n30r_heldout_task_bank.py | test of archived script | 2026-07-10 |
| tests/bench/test_n30r_smoke_task_bank.py | tests/archive/2026-10/bench/test_n30r_smoke_task_bank.py | test of archived script | 2026-07-10 |
| tests/bench/test_n30r_v1_acceptance_oracle.py | tests/archive/2026-10/bench/test_n30r_v1_acceptance_oracle.py | test of archived script | 2026-07-11 |
| tests/benchmark/test_export_s2t_shadow_policy.py | tests/archive/2026-10/benchmark/test_export_s2t_shadow_policy.py | test of archived script | 2026-05-14 |
| tests/benchmark/test_flash_baseline_summary.py | tests/archive/2026-10/benchmark/test_flash_baseline_summary.py | test of archived script | 2026-05-06 |
| tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py | tests/archive/2026-10/benchmark/test_h5_cloud_fallback_e2e_smoke.py | test of archived script | 2026-06-23 |
| tests/benchmark/test_h5_local_committee_e2e_smoke.py | tests/archive/2026-10/benchmark/test_h5_local_committee_e2e_smoke.py | test of archived script | 2026-06-23 |
| tests/benchmark/test_nexus_value_comparison_report.py | tests/archive/2026-10/benchmark/test_nexus_value_comparison_report.py | test of archived script | 2026-05-02 |
| tests/benchmark/test_refine_route_cost_policy_from_runs.py | tests/archive/2026-10/benchmark/test_refine_route_cost_policy_from_runs.py | test of archived script | 2026-05-14 |
| tests/benchmark/test_route_cost_optimizer.py | tests/archive/2026-10/benchmark/test_route_cost_optimizer.py | test of archived script | 2026-05-14 |
| tests/benchmark/test_route_decision_simulator.py | tests/archive/2026-10/benchmark/test_route_decision_simulator.py | test of archived script | 2026-05-14 |
| tests/benchmark/test_teacher_student_gap_matrix.py | tests/archive/2026-10/benchmark/test_teacher_student_gap_matrix.py | test of archived script | 2026-05-08 |
| tests/benchmark/test_weak_model_closure_plan.py | tests/archive/2026-10/benchmark/test_weak_model_closure_plan.py | test of archived script | 2026-05-07 |
| tests/benchmark/test_weak_model_cost_truth.py | tests/archive/2026-10/benchmark/test_weak_model_cost_truth.py | test of archived script | 2026-05-07 |
| tests/benchmark/test_weak_model_long_loop.py | tests/archive/2026-10/benchmark/test_weak_model_long_loop.py | test of archived script | 2026-05-07 |
| tests/ops/test_build_heep_mat_b_blocked_mode_resolution.py | tests/archive/2026-10/ops/test_build_heep_mat_b_blocked_mode_resolution.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_heep_mat_b_final_skill_decisions.py | tests/archive/2026-10/ops/test_build_heep_mat_b_final_skill_decisions.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_heep_mat_b_live_report.py | tests/archive/2026-10/ops/test_build_heep_mat_b_live_report.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_heep_mat_b_update_packets.py | tests/archive/2026-10/ops/test_build_heep_mat_b_update_packets.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_heep_runtime_curation_status.py | tests/archive/2026-10/ops/test_build_heep_runtime_curation_status.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_heep_runtime_default_apply_decision.py | tests/archive/2026-10/ops/test_build_heep_runtime_default_apply_decision.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_publication_readiness_gate.py | tests/archive/2026-10/ops/test_build_publication_readiness_gate.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_sf_current_skill_ssot.py | tests/archive/2026-10/ops/test_build_sf_current_skill_ssot.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_sf_final_capability_skill_settlement.py | tests/archive/2026-10/ops/test_build_sf_final_capability_skill_settlement.py | test of archived script | 2026-05-21 |
| tests/ops/test_build_sf_final_compare_report.py | tests/archive/2026-10/ops/test_build_sf_final_compare_report.py | test of archived script | 2026-05-21 |
| tests/ops/test_build_sf_final_live_compare_matrix.py | tests/archive/2026-10/ops/test_build_sf_final_live_compare_matrix.py | test of archived script | 2026-10-13 |
| tests/ops/test_build_sf_final_live_compare_report.py | tests/archive/2026-10/ops/test_build_sf_final_live_compare_report.py | test of archived script | 2026-05-21 |
| tests/ops/test_build_sf_final_local_skill_compare.py | tests/archive/2026-10/ops/test_build_sf_final_local_skill_compare.py | test of archived script | 2026-05-21 |
| tests/ops/test_build_sf_final_runtime_apply.py | tests/archive/2026-10/ops/test_build_sf_final_runtime_apply.py | test of archived script | 2026-05-22 |
| tests/ops/test_build_sf_replacement_cleanliness_manifest.py | tests/archive/2026-10/ops/test_build_sf_replacement_cleanliness_manifest.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_sf_systematic_current_overlay.py | tests/archive/2026-10/ops/test_build_sf_systematic_current_overlay.py | test of archived script | 2026-05-20 |
| tests/ops/test_build_zero_trust_v2_public_claim_gate_review.py | tests/archive/2026-10/ops/test_build_zero_trust_v2_public_claim_gate_review.py | test of archived script | 2026-05-22 |
| tests/ops/test_evaluate_github_skill_challengers.py | tests/archive/2026-10/ops/test_evaluate_github_skill_challengers.py | test of archived script | 2026-05-20 |
| tests/ops/test_finalize_heep_mat_b_holds.py | tests/archive/2026-10/ops/test_finalize_heep_mat_b_holds.py | test of archived script | 2026-05-20 |
| tests/ops/test_live_vertical_proof_runner.py | tests/archive/2026-10/ops/test_live_vertical_proof_runner.py | test of archived script | 2026-07-25 |
| tests/ops/test_optimize_sf_primary_skill_descriptions.py | tests/archive/2026-10/ops/test_optimize_sf_primary_skill_descriptions.py | test of archived script | 2026-05-20 |
| tests/ops/test_run_heep_live_pilot.py | tests/archive/2026-10/ops/test_run_heep_live_pilot.py | test of archived script | 2026-05-20 |
| tests/ops/test_weak_model_convergence.py | tests/archive/2026-10/ops/test_weak_model_convergence.py | test of archived script | 2026-05-09 |
| tests/ops/test_zero_trust_v2_report_dag.py | tests/archive/2026-10/ops/test_zero_trust_v2_report_dag.py | test of archived script | 2026-05-22 |
| tests/test_receipt_backfill.py | tests/archive/2026-10/test_receipt_backfill.py | test of archived script | 2026-05-27 |
