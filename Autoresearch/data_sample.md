# Nexus Autonomous GAN Research Data Sample

Generated at: 2026-03-27 (Asia/Taipei)  
Source root: `/Users/jameschen/Workspace/nexus/.nexus`

## Inventory Snapshot

- `metrics/health_explain_timeseries.jsonl`: 30 lines
- `knowledge/policy_memory.jsonl`: 23 lines

Note: Timeseries now reaches the minimum baseline window (30).  
Current signal quality is still low (mostly cold-start/UNKNOWN), so treat this as v0 baseline for parser + simulator plumbing.

## Latest Baseline Stats (last 30 rows)

- `rows_last_window`: 30
- `snapshot_status`: `UNKNOWN` x 30
- `avg_snapshot_score`: 0.0
- `avg_gan_alignment`: 0.0
- `discriminator_checks > 0`: 0 rows
- `learning_frozen=true`: 0 rows

---

## Sample A: health_explain_timeseries.jsonl (last 50)

Path: `/Users/jameschen/Workspace/nexus/.nexus/metrics/health_explain_timeseries.jsonl`

```json
{"ts_utc": "2026-03-27T13:05:35.899448+00:00", "snapshot_score": 0.0, "snapshot_status": "UNKNOWN", "pipeline_health": 0.0, "phase_health": {"P": 0.0, "X": 0.0, "D": 0.0, "R": 0.0, "A": 0.0, "C": 0.0}, "anti_hallucination": {"last_review_status": "", "patch_generated": false, "patch_apply_success": false, "proof_type": "", "proof_present": false, "phantom_success_reason": ""}, "learning": {"frozen": false, "freeze_reasons": [], "ingest_status": "", "curiosity_score": 0.0, "pattern_reuse_rate": 0.0, "lesson_quality": 0.0, "next_run_hit_rate": 0.0}, "self_healing": {"cycle_status": "", "diagnosis_kind": "", "after_diagnosis_kind": "", "phase_route": [], "route_before": [], "route_after": [], "route_weights": {}, "policy_sync": ""}, "adversarial_metrics": {"discriminator_checks": 0, "discriminator_block_count": 0, "discriminator_pass_count": 0, "discriminator_block_rate": 0.0, "discriminator_pass_rate": 0.0, "generator_success_window": 0, "generator_success_rate": 0.0, "gan_alignment_score": 0.0}, "notes": []}
{"ts_utc": "2026-03-27T13:05:52.004094+00:00", "snapshot_score": 0.0, "snapshot_status": "UNKNOWN", "pipeline_health": 0.0, "phase_health": {"P": 0.0, "X": 0.0, "D": 0.0, "R": 0.0, "A": 0.0, "C": 0.0}, "anti_hallucination": {"last_review_status": "", "patch_generated": false, "patch_apply_success": false, "proof_type": "", "proof_present": false, "phantom_success_reason": ""}, "learning": {"frozen": false, "freeze_reasons": [], "ingest_status": "", "curiosity_score": 0.0, "pattern_reuse_rate": 0.0, "lesson_quality": 0.0, "next_run_hit_rate": 0.0}, "self_healing": {"cycle_status": "", "diagnosis_kind": "", "after_diagnosis_kind": "", "phase_route": [], "route_before": [], "route_after": [], "route_weights": {}, "policy_sync": ""}, "adversarial_metrics": {"discriminator_checks": 0, "discriminator_block_count": 0, "discriminator_pass_count": 0, "discriminator_block_rate": 0.0, "discriminator_pass_rate": 0.0, "generator_success_window": 0, "generator_success_rate": 0.0, "gan_alignment_score": 0.0}, "notes": []}
```

---

## Sample B: policy_memory.jsonl (last 50)

Path: `/Users/jameschen/Workspace/nexus/.nexus/knowledge/policy_memory.jsonl`

```json
{"rule_id": "POL-429", "condition": "HTTP 429 Quota Exceeded", "action": "Implement exponential backoff. Increase delay by 2x for each failure.", "confidence": 0.95, "status": "validated"}
{"rule_id": "POL-401", "condition": "HTTP 401 Unauthorized / OAuth Expired", "action": "Trigger 'nexus:auth --refresh' and notify orchestrator.", "confidence": 0.9, "status": "validated"}
{"rule_id": "POL-OS", "condition": "File operations using 'os' module", "action": "Prefer 'pathlib' for modern path handling and cross-platform compatibility.", "confidence": 0.85, "status": "validated"}
{"id": "POL-AUTO-1773998998-0", "pattern": "Fix missing os import in research.py", "trigger_desc": "Cluster centered around: Fix missing os import in research.py", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "55"}, "zero_decay": false, "evidence_link": "feature-1773904384", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.727638", "last_used_at": null}
{"id": "POL-AUTO-1773998998-1", "pattern": "Add a health check endpoint to the API", "trigger_desc": "Cluster centered around: Add a health check endpoint to the API", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "71"}, "zero_decay": false, "evidence_link": "feature-1773904741", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.727987", "last_used_at": null}
{"id": "POL-AUTO-1773998998-2", "pattern": "Fix DI registration conflict in state_io.py", "trigger_desc": "Cluster centered around: Fix DI registration conflict in state_io.py", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "69"}, "zero_decay": false, "evidence_link": "bug-1773904754", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728040", "last_used_at": null}
{"id": "POL-AUTO-1773998998-3", "pattern": "Verify fast mode skips X phase when no external info is needed", "trigger_desc": "Cluster centered around: Verify fast mode skips X phase when no external info is needed", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "63"}, "zero_decay": false, "evidence_link": "feature-1773904767", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728082", "last_used_at": null}
{"id": "POL-AUTO-1773998998-4", "pattern": "Verify 'strict' audit level rejects sub-standard code", "trigger_desc": "Cluster centered around: Verify 'strict' audit level rejects sub-standard code", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "65"}, "zero_decay": false, "evidence_link": "bug-1773904781", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728121", "last_used_at": null}
{"id": "POL-AUTO-1773998998-5", "pattern": "Ensure .nexus/knowledge assets are never purged", "trigger_desc": "Cluster centered around: Ensure .nexus/knowledge assets are never purged", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "64"}, "zero_decay": false, "evidence_link": "bug-1773904797", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728159", "last_used_at": null}
{"id": "POL-AUTO-1773998998-6", "pattern": "Trigger Dr. Claw when audit fails on strike 3", "trigger_desc": "Cluster centered around: Trigger Dr. Claw when audit fails on strike 3", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "65"}, "zero_decay": false, "evidence_link": "bug-1773904803", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728199", "last_used_at": null}
{"id": "POL-AUTO-1773998998-7", "pattern": "Verify Wheel-Shift correctly selects domain models", "trigger_desc": "Cluster centered around: Verify Wheel-Shift correctly selects domain models", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "63"}, "zero_decay": false, "evidence_link": "feature-1773904813", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728242", "last_used_at": null}
{"id": "POL-AUTO-1773998998-8", "pattern": "Verify state transition guard blocks invalid bypasses", "trigger_desc": "Cluster centered around: Verify state transition guard blocks invalid bypasses", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "61"}, "zero_decay": false, "evidence_link": "feature-1773904827", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728278", "last_used_at": null}
{"id": "POL-AUTO-1773998998-9", "pattern": "Complete Nexus full lifecycle audit with research and deep repair", "trigger_desc": "Cluster centered around: Complete Nexus full lifecycle audit with research and deep repair", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "59"}, "zero_decay": false, "evidence_link": "feature-1773904835", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728314", "last_used_at": null}
{"id": "POL-AUTO-1773998998-10", "pattern": "OFF-006", "trigger_desc": "Cluster centered around: OFF-006", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "6"}, "zero_decay": false, "evidence_link": "bug-1773908650", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728328", "last_used_at": null}
{"id": "POL-AUTO-1773998998-11", "pattern": "OFF-001", "trigger_desc": "Cluster centered around: OFF-001", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "11"}, "zero_decay": false, "evidence_link": "bug-1773917885", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728346", "last_used_at": null}
{"id": "POL-AUTO-1773998998-12", "pattern": "TRU-101-TOKEN", "trigger_desc": "Cluster centered around: TRU-101-TOKEN", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "2"}, "zero_decay": false, "evidence_link": "bug-1773917924", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728357", "last_used_at": null}
{"id": "POL-AUTO-1773998998-13", "pattern": "Refactor nexus/engine/pipeline.py to use the new EventBus in nexus/core/events.py for P-X-D-R-A-C phases. Ensure all PhaseHandlers are triggered via events instead of direct calls.", "trigger_desc": "Cluster centered around: Refactor nexus/engine/pipeline.py to use the new EventBus in nexus/core/events.py for P-X-D-R-A-C phases. Ensure all PhaseHandlers are triggered via events instead of direct calls.", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "1"}, "zero_decay": false, "evidence_link": "feature-1773920334", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728369", "last_used_at": null}
{"id": "POL-AUTO-1773998998-14", "pattern": "Create nexus/core/events.py with a robust EventBus and NexusEvent contract supporting legacy emit() and new publish()", "trigger_desc": "Cluster centered around: Create nexus/core/events.py with a robust EventBus and NexusEvent contract supporting legacy emit() and new publish()", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "8"}, "zero_decay": false, "evidence_link": "feature-1773920506", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728384", "last_used_at": null}
{"id": "POL-AUTO-1773998998-15", "pattern": "index.task.1", "trigger_desc": "Cluster centered around: index.task.1", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "12"}, "zero_decay": false, "evidence_link": "feature-1773921468", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728399", "last_used_at": null}
{"id": "POL-AUTO-1773998998-16", "pattern": "test basic repair", "trigger_desc": "Cluster centered around: test basic repair", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "1"}, "zero_decay": false, "evidence_link": "bug-1773975585", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728410", "last_used_at": null}
{"id": "POL-AUTO-1773998998-17", "pattern": "OFF-003", "trigger_desc": "Cluster centered around: OFF-003", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "9"}, "zero_decay": false, "evidence_link": "bug-1773978643", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728424", "last_used_at": null}
{"id": "POL-AUTO-1773998998-18", "pattern": "OFF-005", "trigger_desc": "Cluster centered around: OFF-005", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "7"}, "zero_decay": false, "evidence_link": "bug-1773979531", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728438", "last_used_at": null}
{"id": "POL-AUTO-1773998998-19", "pattern": "OFF-007", "trigger_desc": "Cluster centered around: OFF-007", "remedy": "Apply successful fix from evidence link", "priority": 10, "contextual_anchors": {"path_pattern": "*", "cluster_size": "5"}, "zero_decay": false, "evidence_link": "bug-1773979572", "confidence": 1.0, "status": "candidate", "created_at": "2026-03-20T17:29:58.728449", "last_used_at": null}
```

---

## Recommended Next Collection Step

Run this every cycle to build enough baseline:

```bash
cd /Users/jameschen/Workspace/nexus
uv run scripts/engine/nexus_cli.py nexus:health explain --output json
```

To collect richer (non-zero) adversarial signals, run real governance tasks between explain calls (not explain-only loops), then recalibrate after another 30-50 rows.
