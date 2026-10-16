# Archive manifest: legacy top-level dirs, 2026-10 (batch 1c)

Archived 2026-10-16. Pure git mv; nothing deleted. Pre-move ref: archive/2026-10-16-batch-1c-pre.

Target: <dir>/<rel> -> archive/legacy-2026-10/<dir>/<rel>. Class ARCHIVE in ~/Workspace/nexus-handoffs/2026-10-13-online-ab/ARCHIVE_CLASSIFICATION_20261016_toplevel.tsv. Re-verified at archive time by path/import/basename scans of nexus/, tests/, scripts/ (non-archive), .github/, .agents/ and config files, plus sys.path/parents checks and .gitmodules/pyproject/pyright/ignore-file checks.

## Directories moved

| dir | files | evidence |
|---|---|---|
| .ai/ | 3 | 3 files from 2026-04, no refs |
| astropy/ | 1 | 1 file astropy/utils/_compiler.py (empty-ish stub, 2 lines); code mentions are astropy-the-target-repo paths, not this dir |
| demo/ | 1 | 1 file demo/kubernetes_demo.md; scripts/demo_pipeline.py only prints the string "demo/skidiy-pr.md" |
| ebpf_policy/ | 1 | no import/read/CI/test reference found |
| gemini-codex-dual-gate/ | 35 | no import/read/CI/test reference found |
| legacy/ | 1 | 1 file legacy/logmemory.py (mode 100755), no imports; mentioned in 2026-09-20 product-topology note and assessment |
| memory/ | 2 | top-level duplicate of live nexus/core/memory; no `import memory` |
| nexus-chart/ | 5 | no import/read/CI/test reference found |
| nexus_agent_brain_hub/ | 33 | no import/read/CI/test reference found |
| nexus_github_pr_vault/ | 10 | no import/read/CI/test reference found |
| nexus_sota_records/ | 70 | no import/read/CI/test reference found |
| optimize/ | 2 | top-level duplicate of live nexus/core/optimize; no `import optimize`; test refs in full_workspace_xray.md are to nexus.core.optimize |
| patches/ | 31 | no import/read/CI/test reference found |
| phase_metrics/ | 5 | no import/read/CI/test reference found |
| policy/ | 1 | 1 file policy/learning.py; live module is nexus/core/policy; only MUSE_*SPEC.md and 2026-09-08 ChatGPT handoff mention it |
| reports/ | 2 | 2 files (2026-03/05 status reports); root reports/ is also a runtime output dir name used generically by benches; no tracked-file reads |
| research_lab/ | 6 | no import/read/CI/test reference found |
| results/ | 8 | no import/read/CI/test reference found |
| run_test/ | 1 | no import/read/CI/test reference found |
| rust_specs/ | 1 | no import/read/CI/test reference found |
| self_test_zone/ | 2 | no import/read/CI/test reference found |
| sre-runbook/ | 9 | no import/read/CI/test reference found |
| trials/ | 7 | no import/read/CI/test reference found |
| verification-evidence/ | 5 | no import/read/CI/test reference found |

Files: 242

| original path | new path | last commit |
|---|---|---|
| .ai/plan.md | archive/legacy-2026-10/.ai/plan.md | 2026-04-18 |
| .ai/state.json | archive/legacy-2026-10/.ai/state.json | 2026-04-18 |
| .ai/task.md | archive/legacy-2026-10/.ai/task.md | 2026-04-18 |
| astropy/utils/_compiler.py | archive/legacy-2026-10/astropy/utils/_compiler.py | 2026-06-01 |
| demo/kubernetes_demo.md | archive/legacy-2026-10/demo/kubernetes_demo.md | 2026-03-26 |
| ebpf_policy/sandbox_policy.bpftrace | archive/legacy-2026-10/ebpf_policy/sandbox_policy.bpftrace | 2026-03-26 |
| gemini-codex-dual-gate/GEMINI.md | archive/legacy-2026-10/gemini-codex-dual-gate/GEMINI.md | 2026-04-18 |
| gemini-codex-dual-gate/commands/codex-final-audit.toml | archive/legacy-2026-10/gemini-codex-dual-gate/commands/codex-final-audit.toml | 2026-04-18 |
| gemini-codex-dual-gate/commands/gemini-self-review.toml | archive/legacy-2026-10/gemini-codex-dual-gate/commands/gemini-self-review.toml | 2026-04-18 |
| gemini-codex-dual-gate/commands/implement-closed-loop.toml | archive/legacy-2026-10/gemini-codex-dual-gate/commands/implement-closed-loop.toml | 2026-04-18 |
| gemini-codex-dual-gate/commands/implement-from-plan.toml | archive/legacy-2026-10/gemini-codex-dual-gate/commands/implement-from-plan.toml | 2026-04-18 |
| gemini-codex-dual-gate/commands/plan-with-codex.toml | archive/legacy-2026-10/gemini-codex-dual-gate/commands/plan-with-codex.toml | 2026-04-18 |
| gemini-codex-dual-gate/gemini-extension.json | archive/legacy-2026-10/gemini-codex-dual-gate/gemini-extension.json | 2026-04-18 |
| gemini-codex-dual-gate/scripts/codex_final_audit.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/codex_final_audit.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/gemini_self_review.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/gemini_self_review.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/implement_closed_loop.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/implement_closed_loop.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/implement_from_plan.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/implement_from_plan.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/lib/artifact.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/lib/artifact.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/lib/gate.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/lib/gate.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/lib/lesson_writeback.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/lib/lesson_writeback.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/lib/state.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/lib/state.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/plan_with_codex.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/plan_with_codex.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/tests/test_codex_audit_retry.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/tests/test_codex_audit_retry.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/tests/test_happy_path.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/tests/test_happy_path.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/tests/test_high_bar_gate.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/tests/test_high_bar_gate.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/tests/test_official_writeback.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/tests/test_official_writeback.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/tests/test_scoring_writeback.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/tests/test_scoring_writeback.sh | 2026-04-18 |
| gemini-codex-dual-gate/scripts/tests/test_self_review_retry.sh | archive/legacy-2026-10/gemini-codex-dual-gate/scripts/tests/test_self_review_retry.sh | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/acceptance.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/acceptance.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/changed-files.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/changed-files.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/codex-final-audit.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/codex-final-audit.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/codex-plan-review.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/codex-plan-review.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/codex-scorecard.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/codex-scorecard.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/constraints.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/constraints.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/gemini-scorecard.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/gemini-scorecard.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/implementation-report.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/implementation-report.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/lessons.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/lessons.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/plan.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/plan.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/state.json | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/state.json | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/task.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/task.md | 2026-04-18 |
| gemini-codex-dual-gate/templates/.ai/test-results.md | archive/legacy-2026-10/gemini-codex-dual-gate/templates/.ai/test-results.md | 2026-04-18 |
| legacy/logmemory.py | archive/legacy-2026-10/legacy/logmemory.py | 2026-03-18 |
| memory/__init__.py | archive/legacy-2026-10/memory/__init__.py | 2026-03-19 |
| memory/schema.py | archive/legacy-2026-10/memory/schema.py | 2026-03-19 |
| nexus-chart/Chart.yaml | archive/legacy-2026-10/nexus-chart/Chart.yaml | 2026-03-31 |
| nexus-chart/templates/deployment.yaml | archive/legacy-2026-10/nexus-chart/templates/deployment.yaml | 2026-03-31 |
| nexus-chart/templates/hpa.yaml | archive/legacy-2026-10/nexus-chart/templates/hpa.yaml | 2026-03-31 |
| nexus-chart/templates/pvc.yaml | archive/legacy-2026-10/nexus-chart/templates/pvc.yaml | 2026-03-31 |
| nexus-chart/values.yaml | archive/legacy-2026-10/nexus-chart/values.yaml | 2026-03-31 |
| nexus_agent_brain_hub/00_START_HERE_AGENT_OPTIMIZATION.md | archive/legacy-2026-10/nexus_agent_brain_hub/00_START_HERE_AGENT_OPTIMIZATION.md | 2026-04-21 |
| nexus_agent_brain_hub/01_MUSE_PROTO_ENFORCED_V2.4.md | archive/legacy-2026-10/nexus_agent_brain_hub/01_MUSE_PROTO_ENFORCED_V2.4.md | 2026-04-20 |
| nexus_agent_brain_hub/01_SYSTEM_OVERVIEW_AND_GLOSSARY.md | archive/legacy-2026-10/nexus_agent_brain_hub/01_SYSTEM_OVERVIEW_AND_GLOSSARY.md | 2026-04-21 |
| nexus_agent_brain_hub/02_SUPREME_MASTER_LOOP_PXDRAC.md | archive/legacy-2026-10/nexus_agent_brain_hub/02_SUPREME_MASTER_LOOP_PXDRAC.md | 2026-04-22 |
| nexus_agent_brain_hub/03_SYSTEM_OVERVIEW_AND_MATURITY.md | archive/legacy-2026-10/nexus_agent_brain_hub/03_SYSTEM_OVERVIEW_AND_MATURITY.md | 2026-04-20 |
| nexus_agent_brain_hub/04_AGENT_CAPABILITY_AND_BOUNDARIES.md | archive/legacy-2026-10/nexus_agent_brain_hub/04_AGENT_CAPABILITY_AND_BOUNDARIES.md | 2026-04-20 |
| nexus_agent_brain_hub/05_ACCESS_CONTROL_AND_TAC_FIREWALL.md | archive/legacy-2026-10/nexus_agent_brain_hub/05_ACCESS_CONTROL_AND_TAC_FIREWALL.md | 2026-04-21 |
| nexus_agent_brain_hub/06_CORE_ORCHESTRATOR_AND_COORDINATOR.md | archive/legacy-2026-10/nexus_agent_brain_hub/06_CORE_ORCHESTRATOR_AND_COORDINATOR.md | 2026-04-20 |
| nexus_agent_brain_hub/07_TACTICAL_DRONE_ENGINE_AND_BONSAI.md | archive/legacy-2026-10/nexus_agent_brain_hub/07_TACTICAL_DRONE_ENGINE_AND_BONSAI.md | 2026-04-20 |
| nexus_agent_brain_hub/08_CAMPAIGN_GENERAL_AND_DAG_PLANNING.md | archive/legacy-2026-10/nexus_agent_brain_hub/08_CAMPAIGN_GENERAL_AND_DAG_PLANNING.md | 2026-04-20 |
| nexus_agent_brain_hub/08_HALLUCINATION_GUARD_AND_HI_AUDIT.md | archive/legacy-2026-10/nexus_agent_brain_hub/08_HALLUCINATION_GUARD_AND_HI_AUDIT.md | 2026-04-21 |
| nexus_agent_brain_hub/09_SKILL_FORGE_AND_JIT_ASSEMBLY.md | archive/legacy-2026-10/nexus_agent_brain_hub/09_SKILL_FORGE_AND_JIT_ASSEMBLY.md | 2026-04-20 |
| nexus_agent_brain_hub/10_FLEET_COMMAND_AND_SWARM_ADAPTERS.md | archive/legacy-2026-10/nexus_agent_brain_hub/10_FLEET_COMMAND_AND_SWARM_ADAPTERS.md | 2026-04-20 |
| nexus_agent_brain_hub/11_MSA_ROUTING_AND_LATENT_MEMORY.md | archive/legacy-2026-10/nexus_agent_brain_hub/11_MSA_ROUTING_AND_LATENT_MEMORY.md | 2026-04-20 |
| nexus_agent_brain_hub/12_LANCEDB_AND_VECTOR_KNOWLEDGE_STORE.md | archive/legacy-2026-10/nexus_agent_brain_hub/12_LANCEDB_AND_VECTOR_KNOWLEDGE_STORE.md | 2026-04-20 |
| nexus_agent_brain_hub/13_WISDOM_LAYER_AND_BAYESIAN_OPTIMIZATION.md | archive/legacy-2026-10/nexus_agent_brain_hub/13_WISDOM_LAYER_AND_BAYESIAN_OPTIMIZATION.md | 2026-04-20 |
| nexus_agent_brain_hub/14_KNOWLEDGE_INGESTION_AND_CITATION.md | archive/legacy-2026-10/nexus_agent_brain_hub/14_KNOWLEDGE_INGESTION_AND_CITATION.md | 2026-04-20 |
| nexus_agent_brain_hub/15_CONTEXT_SCORING_AND_TOON_COMPRESSION.md | archive/legacy-2026-10/nexus_agent_brain_hub/15_CONTEXT_SCORING_AND_TOON_COMPRESSION.md | 2026-04-20 |
| nexus_agent_brain_hub/16_STATE_LIFECYCLE_AND_METABOLISM.md | archive/legacy-2026-10/nexus_agent_brain_hub/16_STATE_LIFECYCLE_AND_METABOLISM.md | 2026-04-20 |
| nexus_agent_brain_hub/17_CRITIQUE_ENGINE_AND_ANTI_RAT.md | archive/legacy-2026-10/nexus_agent_brain_hub/17_CRITIQUE_ENGINE_AND_ANTI_RAT.md | 2026-04-20 |
| nexus_agent_brain_hub/18_TASK_LINEAGE_AND_DAG_PROVENANCE.md | archive/legacy-2026-10/nexus_agent_brain_hub/18_TASK_LINEAGE_AND_DAG_PROVENANCE.md | 2026-04-20 |
| nexus_agent_brain_hub/19_INTEGRATED_TESTING_GAUNTLET.md | archive/legacy-2026-10/nexus_agent_brain_hub/19_INTEGRATED_TESTING_GAUNTLET.md | 2026-04-20 |
| nexus_agent_brain_hub/20_HALLUCINATION_GUARD_AND_ACCEPTANCE.md | archive/legacy-2026-10/nexus_agent_brain_hub/20_HALLUCINATION_GUARD_AND_ACCEPTANCE.md | 2026-04-20 |
| nexus_agent_brain_hub/21_CI_RELEASE_GATE_AND_CLOSEOUT.md | archive/legacy-2026-10/nexus_agent_brain_hub/21_CI_RELEASE_GATE_AND_CLOSEOUT.md | 2026-04-20 |
| nexus_agent_brain_hub/22_COMPLIANCE_AND_TRUTH_CLAIMS.md | archive/legacy-2026-10/nexus_agent_brain_hub/22_COMPLIANCE_AND_TRUTH_CLAIMS.md | 2026-04-20 |
| nexus_agent_brain_hub/23_TRUTH_VALIDATOR_AND_PHYSICAL_VERDICT.md | archive/legacy-2026-10/nexus_agent_brain_hub/23_TRUTH_VALIDATOR_AND_PHYSICAL_VERDICT.md | 2026-04-20 |
| nexus_agent_brain_hub/24_CLI_SURFACE_AND_COMMAND_MAPS.md | archive/legacy-2026-10/nexus_agent_brain_hub/24_CLI_SURFACE_AND_COMMAND_MAPS.md | 2026-04-20 |
| nexus_agent_brain_hub/25_LAUNCH_SOP_AND_SCRIPTS_INDEX.md | archive/legacy-2026-10/nexus_agent_brain_hub/25_LAUNCH_SOP_AND_SCRIPTS_INDEX.md | 2026-04-20 |
| nexus_agent_brain_hub/26_WORKTREE_AND_ISOLATION_STRATEGIES.md | archive/legacy-2026-10/nexus_agent_brain_hub/26_WORKTREE_AND_ISOLATION_STRATEGIES.md | 2026-04-20 |
| nexus_agent_brain_hub/27_ERROR_PLAYBOOK_AND_RECOVERY.md | archive/legacy-2026-10/nexus_agent_brain_hub/27_ERROR_PLAYBOOK_AND_RECOVERY.md | 2026-04-20 |
| nexus_agent_brain_hub/28_UNIFIED_SERVICE_REGISTRY_AND_MESH.md | archive/legacy-2026-10/nexus_agent_brain_hub/28_UNIFIED_SERVICE_REGISTRY_AND_MESH.md | 2026-04-22 |
| nexus_agent_brain_hub/29_EVOLUTION_AND_OPTIMIZATION_SPEC.md | archive/legacy-2026-10/nexus_agent_brain_hub/29_EVOLUTION_AND_OPTIMIZATION_SPEC.md | 2026-04-20 |
| nexus_agent_brain_hub/30_API_AND_SDK_QUICKSTART_GUIDE.md | archive/legacy-2026-10/nexus_agent_brain_hub/30_API_AND_SDK_QUICKSTART_GUIDE.md | 2026-04-21 |
| nexus_github_pr_vault/actions_pr_186714.md | archive/legacy-2026-10/nexus_github_pr_vault/actions_pr_186714.md | 2026-03-24 |
| nexus_github_pr_vault/kubernetes_pr_112345.md | archive/legacy-2026-10/nexus_github_pr_vault/kubernetes_pr_112345.md | 2026-03-24 |
| nexus_github_pr_vault/linux_pr_218472.md | archive/legacy-2026-10/nexus_github_pr_vault/linux_pr_218472.md | 2026-03-24 |
| nexus_github_pr_vault/nodejs_pr_5678.md | archive/legacy-2026-10/nexus_github_pr_vault/nodejs_pr_5678.md | 2026-03-24 |
| nexus_github_pr_vault/qiskit_pr_2345.md | archive/legacy-2026-10/nexus_github_pr_vault/qiskit_pr_2345.md | 2026-03-24 |
| nexus_github_pr_vault/react_pr_28901.md | archive/legacy-2026-10/nexus_github_pr_vault/react_pr_28901.md | 2026-03-24 |
| nexus_github_pr_vault/rust_pr_123456.md | archive/legacy-2026-10/nexus_github_pr_vault/rust_pr_123456.md | 2026-03-24 |
| nexus_github_pr_vault/tensorflow_pr_67890.md | archive/legacy-2026-10/nexus_github_pr_vault/tensorflow_pr_67890.md | 2026-03-24 |
| nexus_github_pr_vault/tokio_pr_1890.md | archive/legacy-2026-10/nexus_github_pr_vault/tokio_pr_1890.md | 2026-03-24 |
| nexus_github_pr_vault/v8_pr_9876.md | archive/legacy-2026-10/nexus_github_pr_vault/v8_pr_9876.md | 2026-03-24 |
| nexus_sota_records/README.md | archive/legacy-2026-10/nexus_sota_records/README.md | 2026-04-08 |
| nexus_sota_records/blackhole/apple-m4-jit.md | archive/legacy-2026-10/nexus_sota_records/blackhole/apple-m4-jit.md | 2026-03-24 |
| nexus_sota_records/blackhole/google-tpu-mlir.md | archive/legacy-2026-10/nexus_sota_records/blackhole/google-tpu-mlir.md | 2026-03-24 |
| nexus_sota_records/blackhole/linux-scheduler-deadlock.md | archive/legacy-2026-10/nexus_sota_records/blackhole/linux-scheduler-deadlock.md | 2026-03-24 |
| nexus_sota_records/blackhole/nvidia-cuda-race.md | archive/legacy-2026-10/nexus_sota_records/blackhole/nvidia-cuda-race.md | 2026-03-24 |
| nexus_sota_records/blackhole/openai-reasoning-verifier.md | archive/legacy-2026-10/nexus_sota_records/blackhole/openai-reasoning-verifier.md | 2026-03-24 |
| nexus_sota_records/blackhole/qiskit-optimizer.md | archive/legacy-2026-10/nexus_sota_records/blackhole/qiskit-optimizer.md | 2026-03-24 |
| nexus_sota_records/blackhole/starlink-mesh-routing.md | archive/legacy-2026-10/nexus_sota_records/blackhole/starlink-mesh-routing.md | 2026-03-24 |
| nexus_sota_records/blackhole/swe-bench-plus-hard.md | archive/legacy-2026-10/nexus_sota_records/blackhole/swe-bench-plus-hard.md | 2026-03-24 |
| nexus_sota_records/blackhole/tesla-fsd-fusion.md | archive/legacy-2026-10/nexus_sota_records/blackhole/tesla-fsd-fusion.md | 2026-03-24 |
| nexus_sota_records/blackhole/v8-ftl-compiler.md | archive/legacy-2026-10/nexus_sota_records/blackhole/v8-ftl-compiler.md | 2026-03-24 |
| nexus_sota_records/github_hard/github-actions-186714.md | archive/legacy-2026-10/nexus_sota_records/github_hard/github-actions-186714.md | 2026-03-24 |
| nexus_sota_records/github_hard/kubernetes-112345.md | archive/legacy-2026-10/nexus_sota_records/github_hard/kubernetes-112345.md | 2026-03-24 |
| nexus_sota_records/github_hard/linux-218472.md | archive/legacy-2026-10/nexus_sota_records/github_hard/linux-218472.md | 2026-03-24 |
| nexus_sota_records/github_hard/nodejs-5678.md | archive/legacy-2026-10/nexus_sota_records/github_hard/nodejs-5678.md | 2026-03-24 |
| nexus_sota_records/github_hard/qiskit-2345.md | archive/legacy-2026-10/nexus_sota_records/github_hard/qiskit-2345.md | 2026-03-24 |
| nexus_sota_records/github_hard/react-28901.md | archive/legacy-2026-10/nexus_sota_records/github_hard/react-28901.md | 2026-03-24 |
| nexus_sota_records/github_hard/rust-123456.md | archive/legacy-2026-10/nexus_sota_records/github_hard/rust-123456.md | 2026-03-24 |
| nexus_sota_records/github_hard/tensorflow-67890.md | archive/legacy-2026-10/nexus_sota_records/github_hard/tensorflow-67890.md | 2026-03-24 |
| nexus_sota_records/github_hard/tokio-1890.md | archive/legacy-2026-10/nexus_sota_records/github_hard/tokio-1890.md | 2026-03-24 |
| nexus_sota_records/github_hard/v8-9876.md | archive/legacy-2026-10/nexus_sota_records/github_hard/v8-9876.md | 2026-03-24 |
| nexus_sota_records/hell/aws-lambda-rust.md | archive/legacy-2026-10/nexus_sota_records/hell/aws-lambda-rust.md | 2026-03-24 |
| nexus_sota_records/hell/azure-ad-exploit.md | archive/legacy-2026-10/nexus_sota_records/hell/azure-ad-exploit.md | 2026-03-24 |
| nexus_sota_records/hell/gcp-k8s-operator.md | archive/legacy-2026-10/nexus_sota_records/hell/gcp-k8s-operator.md | 2026-03-24 |
| nexus_sota_records/hell/ios-kernel-patch.md | archive/legacy-2026-10/nexus_sota_records/hell/ios-kernel-patch.md | 2026-03-24 |
| nexus_sota_records/hell/linux-cve-2026-1234.md | archive/legacy-2026-10/nexus_sota_records/hell/linux-cve-2026-1234.md | 2026-03-24 |
| nexus_sota_records/hell/openssl-0day.md | archive/legacy-2026-10/nexus_sota_records/hell/openssl-0day.md | 2026-03-24 |
| nexus_sota_records/hell/oracle-db-priv-esc.md | archive/legacy-2026-10/nexus_sota_records/hell/oracle-db-priv-esc.md | 2026-03-24 |
| nexus_sota_records/hell/salesforce-apex-injection.md | archive/legacy-2026-10/nexus_sota_records/hell/salesforce-apex-injection.md | 2026-03-24 |
| nexus_sota_records/hell/sap-hana-rce.md | archive/legacy-2026-10/nexus_sota_records/hell/sap-hana-rce.md | 2026-03-24 |
| nexus_sota_records/hell/v8-sandbox-escape.md | archive/legacy-2026-10/nexus_sota_records/hell/v8-sandbox-escape.md | 2026-03-24 |
| nexus_sota_records/lite/django__django-11133.md | archive/legacy-2026-10/nexus_sota_records/lite/django__django-11133.md | 2026-03-24 |
| nexus_sota_records/lite/django__django-12747.md | archive/legacy-2026-10/nexus_sota_records/lite/django__django-12747.md | 2026-03-24 |
| nexus_sota_records/lite/django__django-15789.md | archive/legacy-2026-10/nexus_sota_records/lite/django__django-15789.md | 2026-03-24 |
| nexus_sota_records/lite/django__django-15996.md | archive/legacy-2026-10/nexus_sota_records/lite/django__django-15996.md | 2026-03-24 |
| nexus_sota_records/lite/django__django-16379.md | archive/legacy-2026-10/nexus_sota_records/lite/django__django-16379.md | 2026-03-24 |
| nexus_sota_records/lite/matplotlib__matplotlib-23562.md | archive/legacy-2026-10/nexus_sota_records/lite/matplotlib__matplotlib-23562.md | 2026-03-24 |
| nexus_sota_records/lite/sphinx-doc__sphinx-8282.md | archive/legacy-2026-10/nexus_sota_records/lite/sphinx-doc__sphinx-8282.md | 2026-03-24 |
| nexus_sota_records/lite/sympy__sympy-13437.md | archive/legacy-2026-10/nexus_sota_records/lite/sympy__sympy-13437.md | 2026-03-24 |
| nexus_sota_records/lite/sympy__sympy-14024.md | archive/legacy-2026-10/nexus_sota_records/lite/sympy__sympy-14024.md | 2026-03-24 |
| nexus_sota_records/lite/sympy__sympy-24909.md | archive/legacy-2026-10/nexus_sota_records/lite/sympy__sympy-24909.md | 2026-03-24 |
| nexus_sota_records/nexus_blackhole_10_combined.md | archive/legacy-2026-10/nexus_sota_records/nexus_blackhole_10_combined.md | 2026-03-24 |
| nexus_sota_records/nexus_github_hard_10_combined.md | archive/legacy-2026-10/nexus_sota_records/nexus_github_hard_10_combined.md | 2026-03-24 |
| nexus_sota_records/nexus_github_pr_bible.md | archive/legacy-2026-10/nexus_sota_records/nexus_github_pr_bible.md | 2026-03-24 |
| nexus_sota_records/nexus_github_pr_links.md | archive/legacy-2026-10/nexus_sota_records/nexus_github_pr_links.md | 2026-03-24 |
| nexus_sota_records/nexus_github_pr_live_links.md | archive/legacy-2026-10/nexus_sota_records/nexus_github_pr_live_links.md | 2026-03-24 |
| nexus_sota_records/nexus_github_pr_upstream_bible.md | archive/legacy-2026-10/nexus_sota_records/nexus_github_pr_upstream_bible.md | 2026-03-24 |
| nexus_sota_records/nexus_master_benchmark_60_GOD.jsonl | archive/legacy-2026-10/nexus_sota_records/nexus_master_benchmark_60_GOD.jsonl | 2026-03-24 |
| nexus_sota_records/nexus_power_analysis.md | archive/legacy-2026-10/nexus_sota_records/nexus_power_analysis.md | 2026-03-24 |
| nexus_sota_records/nexus_power_analysis_zh.md | archive/legacy-2026-10/nexus_sota_records/nexus_power_analysis_zh.md | 2026-03-24 |
| nexus_sota_records/pro/ansible-7777.md | archive/legacy-2026-10/nexus_sota_records/pro/ansible-7777.md | 2026-03-24 |
| nexus_sota_records/pro/elasticsearch-1011.md | archive/legacy-2026-10/nexus_sota_records/pro/elasticsearch-1011.md | 2026-03-24 |
| nexus_sota_records/pro/go-9999.md | archive/legacy-2026-10/nexus_sota_records/pro/go-9999.md | 2026-03-24 |
| nexus_sota_records/pro/kubernetes-12345.md | archive/legacy-2026-10/nexus_sota_records/pro/kubernetes-12345.md | 2026-03-24 |
| nexus_sota_records/pro/nodejs-5678.md | archive/legacy-2026-10/nexus_sota_records/pro/nodejs-5678.md | 2026-03-24 |
| nexus_sota_records/pro/pytorch-6789.md | archive/legacy-2026-10/nexus_sota_records/pro/pytorch-6789.md | 2026-03-24 |
| nexus_sota_records/pro/react-3345.md | archive/legacy-2026-10/nexus_sota_records/pro/react-3345.md | 2026-03-24 |
| nexus_sota_records/pro/spring-boot-1456.md | archive/legacy-2026-10/nexus_sota_records/pro/spring-boot-1456.md | 2026-03-24 |
| nexus_sota_records/pro/tensorflow-2789.md | archive/legacy-2026-10/nexus_sota_records/pro/tensorflow-2789.md | 2026-03-24 |
| nexus_sota_records/pro/tokio-8901.md | archive/legacy-2026-10/nexus_sota_records/pro/tokio-8901.md | 2026-03-24 |
| nexus_sota_records/ultimate/chart-render-002.md | archive/legacy-2026-10/nexus_sota_records/ultimate/chart-render-002.md | 2026-03-24 |
| nexus_sota_records/ultimate/logo-svg-004.md | archive/legacy-2026-10/nexus_sota_records/ultimate/logo-svg-004.md | 2026-03-24 |
| nexus_sota_records/ultimate/mobile-pwa-005.md | archive/legacy-2026-10/nexus_sota_records/ultimate/mobile-pwa-005.md | 2026-03-24 |
| nexus_sota_records/ultimate/nextjs-64532.md | archive/legacy-2026-10/nexus_sota_records/ultimate/nextjs-64532.md | 2026-03-24 |
| nexus_sota_records/ultimate/prisma-23456.md | archive/legacy-2026-10/nexus_sota_records/ultimate/prisma-23456.md | 2026-03-24 |
| nexus_sota_records/ultimate/react-28901.md | archive/legacy-2026-10/nexus_sota_records/ultimate/react-28901.md | 2026-03-24 |
| nexus_sota_records/ultimate/tailwind-13456.md | archive/legacy-2026-10/nexus_sota_records/ultimate/tailwind-13456.md | 2026-03-24 |
| nexus_sota_records/ultimate/typescript-58901.md | archive/legacy-2026-10/nexus_sota_records/ultimate/typescript-58901.md | 2026-03-24 |
| nexus_sota_records/ultimate/ui-layout-001.md | archive/legacy-2026-10/nexus_sota_records/ultimate/ui-layout-001.md | 2026-03-24 |
| nexus_sota_records/ultimate/video-frame-003.md | archive/legacy-2026-10/nexus_sota_records/ultimate/video-frame-003.md | 2026-03-24 |
| optimize/__init__.py | archive/legacy-2026-10/optimize/__init__.py | 2026-03-19 |
| optimize/loop.py | archive/legacy-2026-10/optimize/loop.py | 2026-03-19 |
| patches/README.md | archive/legacy-2026-10/patches/README.md | 2026-03-24 |
| patches/django__django-11133/base_commit.txt | archive/legacy-2026-10/patches/django__django-11133/base_commit.txt | 2026-03-24 |
| patches/django__django-11133/git_status.txt | archive/legacy-2026-10/patches/django__django-11133/git_status.txt | 2026-03-24 |
| patches/django__django-11133/patch.diff | archive/legacy-2026-10/patches/django__django-11133/patch.diff | 2026-03-24 |
| patches/django__django-12747/base_commit.txt | archive/legacy-2026-10/patches/django__django-12747/base_commit.txt | 2026-03-24 |
| patches/django__django-12747/git_status.txt | archive/legacy-2026-10/patches/django__django-12747/git_status.txt | 2026-03-24 |
| patches/django__django-12747/patch.diff | archive/legacy-2026-10/patches/django__django-12747/patch.diff | 2026-03-24 |
| patches/django__django-15789/base_commit.txt | archive/legacy-2026-10/patches/django__django-15789/base_commit.txt | 2026-03-24 |
| patches/django__django-15789/git_status.txt | archive/legacy-2026-10/patches/django__django-15789/git_status.txt | 2026-03-24 |
| patches/django__django-15789/patch.diff | archive/legacy-2026-10/patches/django__django-15789/patch.diff | 2026-03-24 |
| patches/django__django-15996/base_commit.txt | archive/legacy-2026-10/patches/django__django-15996/base_commit.txt | 2026-03-24 |
| patches/django__django-15996/git_status.txt | archive/legacy-2026-10/patches/django__django-15996/git_status.txt | 2026-03-24 |
| patches/django__django-15996/patch.diff | archive/legacy-2026-10/patches/django__django-15996/patch.diff | 2026-03-24 |
| patches/django__django-16379/base_commit.txt | archive/legacy-2026-10/patches/django__django-16379/base_commit.txt | 2026-03-24 |
| patches/django__django-16379/git_status.txt | archive/legacy-2026-10/patches/django__django-16379/git_status.txt | 2026-03-24 |
| patches/django__django-16379/patch.diff | archive/legacy-2026-10/patches/django__django-16379/patch.diff | 2026-03-24 |
| patches/matplotlib__matplotlib-23562/base_commit.txt | archive/legacy-2026-10/patches/matplotlib__matplotlib-23562/base_commit.txt | 2026-03-24 |
| patches/matplotlib__matplotlib-23562/git_status.txt | archive/legacy-2026-10/patches/matplotlib__matplotlib-23562/git_status.txt | 2026-03-24 |
| patches/matplotlib__matplotlib-23562/patch.diff | archive/legacy-2026-10/patches/matplotlib__matplotlib-23562/patch.diff | 2026-03-24 |
| patches/sphinx-doc__sphinx-8282/base_commit.txt | archive/legacy-2026-10/patches/sphinx-doc__sphinx-8282/base_commit.txt | 2026-03-24 |
| patches/sphinx-doc__sphinx-8282/git_status.txt | archive/legacy-2026-10/patches/sphinx-doc__sphinx-8282/git_status.txt | 2026-03-24 |
| patches/sphinx-doc__sphinx-8282/patch.diff | archive/legacy-2026-10/patches/sphinx-doc__sphinx-8282/patch.diff | 2026-03-24 |
| patches/sympy__sympy-13437/base_commit.txt | archive/legacy-2026-10/patches/sympy__sympy-13437/base_commit.txt | 2026-03-24 |
| patches/sympy__sympy-13437/git_status.txt | archive/legacy-2026-10/patches/sympy__sympy-13437/git_status.txt | 2026-03-24 |
| patches/sympy__sympy-13437/patch.diff | archive/legacy-2026-10/patches/sympy__sympy-13437/patch.diff | 2026-03-24 |
| patches/sympy__sympy-14024/base_commit.txt | archive/legacy-2026-10/patches/sympy__sympy-14024/base_commit.txt | 2026-03-24 |
| patches/sympy__sympy-14024/git_status.txt | archive/legacy-2026-10/patches/sympy__sympy-14024/git_status.txt | 2026-03-24 |
| patches/sympy__sympy-14024/patch.diff | archive/legacy-2026-10/patches/sympy__sympy-14024/patch.diff | 2026-03-24 |
| patches/sympy__sympy-24909/base_commit.txt | archive/legacy-2026-10/patches/sympy__sympy-24909/base_commit.txt | 2026-03-24 |
| patches/sympy__sympy-24909/git_status.txt | archive/legacy-2026-10/patches/sympy__sympy-24909/git_status.txt | 2026-03-24 |
| patches/sympy__sympy-24909/patch.diff | archive/legacy-2026-10/patches/sympy__sympy-24909/patch.diff | 2026-03-24 |
| phase_metrics/bug-1773873376_metrics.json | archive/legacy-2026-10/phase_metrics/bug-1773873376_metrics.json | 2026-03-19 |
| phase_metrics/bug-1773875932_metrics.json | archive/legacy-2026-10/phase_metrics/bug-1773875932_metrics.json | 2026-03-19 |
| phase_metrics/bug-1773880387_metrics.json | archive/legacy-2026-10/phase_metrics/bug-1773880387_metrics.json | 2026-03-19 |
| phase_metrics/bug-1773880491_metrics.json | archive/legacy-2026-10/phase_metrics/bug-1773880491_metrics.json | 2026-03-19 |
| phase_metrics/bug-1773884201_metrics.json | archive/legacy-2026-10/phase_metrics/bug-1773884201_metrics.json | 2026-03-19 |
| policy/learning.py | archive/legacy-2026-10/policy/learning.py | 2026-03-19 |
| reports/agent_status_report_20260318_2135.md | archive/legacy-2026-10/reports/agent_status_report_20260318_2135.md | 2026-03-19 |
| reports/cost_advance_reports/NEXUS_COST_ADVANCE_REPORT.md | archive/legacy-2026-10/reports/cost_advance_reports/NEXUS_COST_ADVANCE_REPORT.md | 2026-05-28 |
| research_lab/EXPERIMENTAL_RESULTS_V1.md | archive/legacy-2026-10/research_lab/EXPERIMENTAL_RESULTS_V1.md | 2026-04-08 |
| research_lab/phase_1_signature/extractor_prototype.py | archive/legacy-2026-10/research_lab/phase_1_signature/extractor_prototype.py | 2026-03-28 |
| research_lab/phase_2_sandbox/mock_proj/src/logic.py | archive/legacy-2026-10/research_lab/phase_2_sandbox/mock_proj/src/logic.py | 2026-03-28 |
| research_lab/phase_2_sandbox/mock_proj/test_logic.py | archive/legacy-2026-10/research_lab/phase_2_sandbox/mock_proj/test_logic.py | 2026-03-28 |
| research_lab/phase_2_sandbox/sandbox_runner.py | archive/legacy-2026-10/research_lab/phase_2_sandbox/sandbox_runner.py | 2026-04-08 |
| research_lab/self_heal_upgrade_handover/HANDOVER_SELF_HEAL_LEARNING_FOUNDATION.md | archive/legacy-2026-10/research_lab/self_heal_upgrade_handover/HANDOVER_SELF_HEAL_LEARNING_FOUNDATION.md | 2026-04-08 |
| results/astropy_cumulative.diff | archive/legacy-2026-10/results/astropy_cumulative.diff | 2026-03-24 |
| results/astropy_truth.diff | archive/legacy-2026-10/results/astropy_truth.diff | 2026-03-24 |
| results/nexus_v16_results.jsonl | archive/legacy-2026-10/results/nexus_v16_results.jsonl | 2026-03-24 |
| results/numpy_cumulative.diff | archive/legacy-2026-10/results/numpy_cumulative.diff | 2026-03-24 |
| results/swe_nexus_v25.5_lite.json | archive/legacy-2026-10/results/swe_nexus_v25.5_lite.json | 2026-04-08 |
| results/sympy_cumulative.diff | archive/legacy-2026-10/results/sympy_cumulative.diff | 2026-03-24 |
| results/sympy_truth.diff | archive/legacy-2026-10/results/sympy_truth.diff | 2026-03-24 |
| results/webarena_nexus_v25.5_test.json | archive/legacy-2026-10/results/webarena_nexus_v25.5_test.json | 2026-04-08 |
| run_test/researchpack.json | archive/legacy-2026-10/run_test/researchpack.json | 2026-03-18 |
| rust_specs/fast_matcher_spec.md | archive/legacy-2026-10/rust_specs/fast_matcher_spec.md | 2026-06-02 |
| self_test_zone/complexity_test.py | archive/legacy-2026-10/self_test_zone/complexity_test.py | 2026-03-24 |
| self_test_zone/science_test.py | archive/legacy-2026-10/self_test_zone/science_test.py | 2026-03-24 |
| sre-runbook/README.md | archive/legacy-2026-10/sre-runbook/README.md | 2026-06-15 |
| sre-runbook/backup.sh | archive/legacy-2026-10/sre-runbook/backup.sh | 2026-04-04 |
| sre-runbook/chaos-drills/chaos-drills.sh | archive/legacy-2026-10/sre-runbook/chaos-drills/chaos-drills.sh | 2026-04-04 |
| sre-runbook/chaos-drills/resilience-report.md | archive/legacy-2026-10/sre-runbook/chaos-drills/resilience-report.md | 2026-04-04 |
| sre-runbook/deploy-p5-day2.sh | archive/legacy-2026-10/sre-runbook/deploy-p5-day2.sh | 2026-04-04 |
| sre-runbook/failover.md | archive/legacy-2026-10/sre-runbook/failover.md | 2026-04-04 |
| sre-runbook/grafana-dashboard.json | archive/legacy-2026-10/sre-runbook/grafana-dashboard.json | 2026-04-04 |
| sre-runbook/restore.sh | archive/legacy-2026-10/sre-runbook/restore.sh | 2026-04-04 |
| sre-runbook/weekly-shadow-report.py | archive/legacy-2026-10/sre-runbook/weekly-shadow-report.py | 2026-04-04 |
| trials/acheron/core/memory.rs | archive/legacy-2026-10/trials/acheron/core/memory.rs | 2026-03-28 |
| trials/acheron/core/mirror.py | archive/legacy-2026-10/trials/acheron/core/mirror.py | 2026-03-28 |
| trials/acheron/core/quantum.rs | archive/legacy-2026-10/trials/acheron/core/quantum.rs | 2026-03-28 |
| trials/acheron/test/test_reflection.py | archive/legacy-2026-10/trials/acheron/test/test_reflection.py | 2026-03-28 |
| trials/acheron/util/bridge.rs | archive/legacy-2026-10/trials/acheron/util/bridge.rs | 2026-03-28 |
| trials/acheron/util/entropy.rs | archive/legacy-2026-10/trials/acheron/util/entropy.rs | 2026-03-28 |
| trials/web_console/index.html | archive/legacy-2026-10/trials/web_console/index.html | 2026-04-02 |
| verification-evidence/flow_machine_full_matrix_report.json | archive/legacy-2026-10/verification-evidence/flow_machine_full_matrix_report.json | 2026-06-20 |
| verification-evidence/promotion_gate_report.json | archive/legacy-2026-10/verification-evidence/promotion_gate_report.json | 2026-06-20 |
| verification-evidence/rollback_drill_report.json | archive/legacy-2026-10/verification-evidence/rollback_drill_report.json | 2026-06-20 |
| verification-evidence/rollback_drill_report.md | archive/legacy-2026-10/verification-evidence/rollback_drill_report.md | 2026-06-20 |
| verification-evidence/rust_mismatch_ledger_summary.json | archive/legacy-2026-10/verification-evidence/rust_mismatch_ledger_summary.json | 2026-06-20 |

## Kept (not moved)

| path | reason |
|---|---|
| Autoresearch/ | nexus/services/xray_service.py:19 default xray target |
| Autoresearch_runtime/ | scripts/ops/brain_loop_closure.py:101 globs Autoresearch_runtime/*.json into the vector DB (726 files; needs an owner decision or a code edit) |
| cases/ | nexus/benchmark/benchmark_runner.py:59,87 and scripts/ci/run_smoke_benchmark.py read cases/catalog.json |
| obsidian/ | nexus/services/memory.py:113 runtime path; tests/test_memory.py |
| pilot_delivery_bundle/ | scripts/ops/skills_emergency_recovery.py:10, pilot_cli_delivery_smoke.py |
| subprojects/ | nexus/engine/governance_bridge.py:252 reads subprojects/nexus-receipt-core/schemas/flow_machine.contract.v1.json |
| tenants/ | scripts/ops/supervisor_engine.py:40 writes tenants/<tenant>/swarm_work.json |
| src/ | nexus/services/m5_local/deterministic_fallback.py:96 searches root/src |
| scratch/ (18 remaining files) | named from scripts/bench/*.json(l), benchmarking/*.jsonl, tests (see scripts/archive/2026-10/ARCHIVE_MANIFEST.md) |
| results/official_verified_ids.txt, results/true_astropy_tasks.txt (non-ASCII names) | impact-map coverage tool cannot match quoted git paths |
| archives/, perf_regression_pack_v22.5/, .obsidian/ | classification batch 2 (each needs a one-line edit in a guard/script/test) |
| repro/, packages/ | gitlinks/submodules (.gitmodules), classification batch 3 |
| KEEP / KEEP-CODE-REF / KEEP-AS-FIXTURE / HOLD dirs | not archive candidates |

## Batch 2 (archives/, perf_regression_pack_v22.5/, .obsidian/)

Evidence: ~/Workspace/nexus-handoffs/2026-10-13-online-ab/ARCHIVE_CLASSIFICATION_20261016.md (batch 2) re-derived on main c48689bb4 by whole-repo basename/path scans; each script moves only together with every test that imports it. Pre-move ref: archive/2026-10-17-batch-2-pre.

Edits: scripts/ops/scope_guard.py drops the perf_regression_pack_v22.5/ allowed prefix (archive/ is allowed). scripts/governance/freeze_v27_2.py (a one-off v27.2 freeze script that writes archives/v27.2/...) is NOT edited: it is unmapped in the impact map, so editing it would force a full-suite plan; it fails if re-run until its path is updated. scripts/ops/nexus_gateway_auto_deploy.py IRRELEVANT_PREFIXES still lists "archives/" (harmless, untouched); .gitnexusignore entries for perf_regression_pack_v22.5/ are now inert.

Files: 45

| original path | new path | class | last commit |
|---|---|---|---|
| archives/v27.1/.gitkeep | archive/legacy-2026-10/archives/v27.1/.gitkeep | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.1/adr_freeze_manifest.json | archive/legacy-2026-10/archives/v27.1/adr_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.1/rollback_and_replay_index.md | archive/legacy-2026-10/archives/v27.1/rollback_and_replay_index.md | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.1/v27.1_archive_bundle.json | archive/legacy-2026-10/archives/v27.1/v27.1_archive_bundle.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.2/v27.2_freeze_manifest.json | archive/legacy-2026-10/archives/v27.2/v27.2_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.3/v27.3_freeze_manifest.json | archive/legacy-2026-10/archives/v27.3/v27.3_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.4/v27.4_freeze_manifest.json | archive/legacy-2026-10/archives/v27.4/v27.4_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.5/v27.5_freeze_manifest.json | archive/legacy-2026-10/archives/v27.5/v27.5_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.6/v27.6_freeze_manifest.json | archive/legacy-2026-10/archives/v27.6/v27.6_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.7/v27.7_freeze_manifest.json | archive/legacy-2026-10/archives/v27.7/v27.7_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.8/v27.8_freeze_manifest.json | archive/legacy-2026-10/archives/v27.8/v27.8_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v27.9/v27.9_freeze_manifest.json | archive/legacy-2026-10/archives/v27.9/v27.9_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| archives/v28.0/v28.0_freeze_manifest.json | archive/legacy-2026-10/archives/v28.0/v28.0_freeze_manifest.json | ARCHIVE dir (batch 2) | 2026-06-04 |
| perf_regression_pack_v22.5/01_PERF_INDEX.md | archive/legacy-2026-10/perf_regression_pack_v22.5/01_PERF_INDEX.md | ARCHIVE dir (batch 2) | 2026-04-08 |
| perf_regression_pack_v22.5/02_REGRESSION_BASELINE_VS_CURRENT.md | archive/legacy-2026-10/perf_regression_pack_v22.5/02_REGRESSION_BASELINE_VS_CURRENT.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/03_WORKLOAD_AND_TEST_CONDITIONS.md | archive/legacy-2026-10/perf_regression_pack_v22.5/03_WORKLOAD_AND_TEST_CONDITIONS.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/04_TRACE_TIMELINE_BREAKDOWN.md | archive/legacy-2026-10/perf_regression_pack_v22.5/04_TRACE_TIMELINE_BREAKDOWN.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/05_ROOT_CAUSE_HYPOTHESIS_MATRIX.md | archive/legacy-2026-10/perf_regression_pack_v22.5/05_ROOT_CAUSE_HYPOTHESIS_MATRIX.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/06_ORCHESTRATOR_CODE_PATHS.md | archive/legacy-2026-10/perf_regression_pack_v22.5/06_ORCHESTRATOR_CODE_PATHS.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/07_GUARD_HEALER_DECISION_CHAIN.md | archive/legacy-2026-10/perf_regression_pack_v22.5/07_GUARD_HEALER_DECISION_CHAIN.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/08_SERIAL_DISPATCH_PROVE.md | archive/legacy-2026-10/perf_regression_pack_v22.5/08_SERIAL_DISPATCH_PROVE.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/09_SYNC_SUBPROCESS_IMPACT.md | archive/legacy-2026-10/perf_regression_pack_v22.5/09_SYNC_SUBPROCESS_IMPACT.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/10_METRICS_SERIALIZATION_OVERHEAD.md | archive/legacy-2026-10/perf_regression_pack_v22.5/10_METRICS_SERIALIZATION_OVERHEAD.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/11_RECOMMENDED_FIX_ASYNC_BLUEPRINT.md | archive/legacy-2026-10/perf_regression_pack_v22.5/11_RECOMMENDED_FIX_ASYNC_BLUEPRINT.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/12_REPRO_AND_VALIDATION_SCRIPTS.md | archive/legacy-2026-10/perf_regression_pack_v22.5/12_REPRO_AND_VALIDATION_SCRIPTS.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/13_REGRESSION_METHOD_RECONCILIATION.md | archive/legacy-2026-10/perf_regression_pack_v22.5/13_REGRESSION_METHOD_RECONCILIATION.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/14_FULL_REQUEST_TRACE_RAW.md | archive/legacy-2026-10/perf_regression_pack_v22.5/14_FULL_REQUEST_TRACE_RAW.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/15_EVIDENCE_GRADE_MATRIX.md | archive/legacy-2026-10/perf_regression_pack_v22.5/15_EVIDENCE_GRADE_MATRIX.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/21_PATCH_REVIEW_RESOLUTION.md | archive/legacy-2026-10/perf_regression_pack_v22.5/21_PATCH_REVIEW_RESOLUTION.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/22_PATCH_C_SAFETY_INVARIANTS.md | archive/legacy-2026-10/perf_regression_pack_v22.5/22_PATCH_C_SAFETY_INVARIANTS.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/23_PATCH_GATE_THRESHOLDS.md | archive/legacy-2026-10/perf_regression_pack_v22.5/23_PATCH_GATE_THRESHOLDS.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/25_PATCH_B_REPORT.md | archive/legacy-2026-10/perf_regression_pack_v22.5/25_PATCH_B_REPORT.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/26_PATCH_C_PARALLEL_REPORT.md | archive/legacy-2026-10/perf_regression_pack_v22.5/26_PATCH_C_PARALLEL_REPORT.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/FINAL_PERFORMANCE_REPAIR_v22.5.md | archive/legacy-2026-10/perf_regression_pack_v22.5/FINAL_PERFORMANCE_REPAIR_v22.5.md | ARCHIVE dir (batch 2) | 2026-04-07 |
| perf_regression_pack_v22.5/LEARNING_LOOP_CLOSED_LOOP_CERTIFICATION.md | archive/legacy-2026-10/perf_regression_pack_v22.5/LEARNING_LOOP_CLOSED_LOOP_CERTIFICATION.md | ARCHIVE dir (batch 2) | 2026-04-08 |
| perf_regression_pack_v22.5/LEARNING_LOOP_MASTER_SPEC.md | archive/legacy-2026-10/perf_regression_pack_v22.5/LEARNING_LOOP_MASTER_SPEC.md | ARCHIVE dir (batch 2) | 2026-04-08 |
| perf_regression_pack_v22.5/README.md | archive/legacy-2026-10/perf_regression_pack_v22.5/README.md | ARCHIVE dir (batch 2) | 2026-04-08 |
| perf_regression_pack_v22.5/SWARM_STATUS_AUDIT_3.705.0.md | archive/legacy-2026-10/perf_regression_pack_v22.5/SWARM_STATUS_AUDIT_3.705.0.md | ARCHIVE dir (batch 2) | 2026-04-08 |
| perf_regression_pack_v22.5/V23_5_MASTER_SPEC.md | archive/legacy-2026-10/perf_regression_pack_v22.5/V23_5_MASTER_SPEC.md | ARCHIVE dir (batch 2) | 2026-04-08 |
| perf_regression_pack_v22.5/metadata.json | archive/legacy-2026-10/perf_regression_pack_v22.5/metadata.json | ARCHIVE dir (batch 2) | 2026-04-08 |
| perf_regression_pack_v22.5/phase36.10_review.md | archive/legacy-2026-10/perf_regression_pack_v22.5/phase36.10_review.md | ARCHIVE dir (batch 2) | 2026-04-08 |
| .obsidian/app.json | archive/legacy-2026-10/.obsidian/app.json | ARCHIVE dir (batch 2) | 2026-03-28 |
| .obsidian/appearance.json | archive/legacy-2026-10/.obsidian/appearance.json | ARCHIVE dir (batch 2) | 2026-03-28 |
| .obsidian/core-plugins.json | archive/legacy-2026-10/.obsidian/core-plugins.json | ARCHIVE dir (batch 2) | 2026-03-28 |
| .obsidian/workspace.json | archive/legacy-2026-10/.obsidian/workspace.json | ARCHIVE dir (batch 2) | 2026-06-06 |
