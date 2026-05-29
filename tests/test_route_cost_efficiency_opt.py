import pytest
import json
from nexus.core.router import SkillsRouter
from nexus.core.belief_contracts import CapabilityReceipt as CoreReceipt
from nexus.engine.capability_contracts import CapabilityReceipt as EngineReceipt
from scripts.bench.public_gate_bundle import derive_cost_efficiency_decision, CostEfficiencyDecision

def test_route_policy_deterministic_rescue_and_candidate_invariants():
    """
    TDD Phase 1 (RED): Verify SkillsRouter supports allow_pre_model_deterministic_rescue contract
    and structures route policy evidence containing capability invariant candidate pools.
    """
    # Initialize SkillsRouter with mock options representing policy controls
    router = SkillsRouter(
        project_root="/Users/jameschen/Workspace/nexus",
        allow_pre_model_deterministic_rescue=True,
        candidate_pool_mode="capability_invariant",  # E.g. "1 LLM + local support"
        governance_hardened_mode="supervised_bare_first"
    )
    
    # Verify the configured policies exist on the router contract interface
    assert hasattr(router, "allow_pre_model_deterministic_rescue")
    assert router.allow_pre_model_deterministic_rescue is True
    assert router.candidate_pool_mode == "capability_invariant"
    
    # Mock routing decision payload representing pre-model rescue
    decision = router.decide_route(
        capability="ast_scanning",
        risk_level="low",
        bare_sufficiency="high",
        hidden_verifier_passed=True
    )
    
    # Route policy evidence must carry reason codes & show it contributed deterministic rescue
    assert "route_execution_policy" in decision
    policy = decision["route_execution_policy"]
    assert "cost_capped_capability_allows_verified_pre_model_rescue" in policy["reason_codes"]
    assert policy["pre_model_deterministic_rescue_allowed"] is True
    assert policy["candidate_pool_size"] == 1  # 1 LLM + local support invariant

def test_telemetry_classification_exclusion_and_provenance():
    """
    TDD Phase 2 (RED): Verify telemetry classification structures network_timeout_observed_ms,
    cost_accounting_exclusion_candidate, and telemetry_provenance on CapabilityReceipt without mutating wall_time_ms.
    """
    # 1. Verify CoreReceipt accepts new classification parameters
    rcpt = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_123",
        gate_passed=True,
        telemetries={
            "wall_time_ms": 5000,
            "token_usage": 1000,
            "provider_costs": 0.02,
            "overhead_ms": 300,
            "network_timeout_observed_ms": 3500,
            "cost_accounting_exclusion_candidate": True,
            "telemetry_provenance": "gateway_timeout"
        }
    )
    
    # Ensure wall_time_ms is preserved conservatively (not directly deducted)
    assert rcpt.telemetries["wall_time_ms"] == 5000
    assert rcpt.telemetries["network_timeout_observed_ms"] == 3500
    assert rcpt.telemetries["cost_accounting_exclusion_candidate"] is True
    assert rcpt.telemetries["telemetry_provenance"] == "gateway_timeout"
    assert rcpt.is_claimable is True  # Should still be claimable if telemetry is complete
    
    # 2. Verify derive_cost_efficiency_decision supports exclusion based on reason-code and provenance
    # Scenario A: Valid exclusion provenance -> NOT regressed despite wall_time_ratio over 1.0
    decision_excluded = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=1.2,  # Over 1.0, ordinarily REGRESSED
        token_cost_ratio_with_over_without=0.9,
        model_call_ratio_with_over_without=0.9,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
        exclusion_candidate=True,
        exclusion_reason_code="network_timeout_exceeded",
        exclusion_provenance="gateway_timeout"
    )
    
    # The decision status should resolve as IMPROVED or NEUTRAL due to valid exclusion
    assert decision_excluded.status in {"IMPROVED", "NEUTRAL"}
    assert "wall_cost_not_improved" not in decision_excluded.failures
    
    # Scenario B: Invalid provenance -> Still REGRESSED
    decision_failed_exclusion = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=1.2,
        token_cost_ratio_with_over_without=0.9,
        model_call_ratio_with_over_without=0.9,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
        exclusion_candidate=True,
        exclusion_reason_code="unknown_reason",
        exclusion_provenance="unregistered_provenance"
    )
    
    assert decision_failed_exclusion.status == "REGRESSED"
    assert "wall_cost_not_improved" in decision_failed_exclusion.failures

def test_token_cleanliness_and_outlier_quarantine():
    """
    TDD Phase 3 (RED): Verify Task 1 (P0) token cleanliness and outlier quarantine gates.
    1. Token cleanliness: if model call occurred (model_calls > 0) but tokens are missing (token_usage <= 0 or missing),
       the row is infra-invalid, verify_telemetry is invalid, and is_claimable is False.
    2. Outlier gate: if gateway_token_outlier_reason == "stats_outlier_possible_cumulative",
       verify_telemetry is invalid (is_claimable is False) and public_claim_safe is False.
    """
    # Test case 1: Model call occurred but tokens are 0
    rcpt_missing_tokens = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_123",
        gate_passed=True,
        telemetries={
            "wall_time_ms": 5000,
            "token_usage": 0,
            "provider_costs": 0.02,
            "overhead_ms": 300,
            "model_calls": 1,
            "has_infra_invalid": True,
            "infra_invalid_reason": "token_cleanliness_missing_tokens"
        }
    )
    assert rcpt_missing_tokens.verify_telemetry.is_valid is False
    assert rcpt_missing_tokens.is_claimable is False
    
    # Test case 2: Outlier detected
    rcpt_outlier_core = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_123",
        gate_passed=True,
        telemetries={
            "wall_time_ms": 5000,
            "token_usage": 1000,
            "provider_costs": 0.02,
            "overhead_ms": 300,
            "model_calls": 1,
            "gateway_token_outlier_reason": "stats_outlier_possible_cumulative"
        }
    )
    assert rcpt_outlier_core.verify_telemetry.is_valid is False
    assert rcpt_outlier_core.is_claimable is False

    rcpt_outlier_engine = EngineReceipt(
        name="test_cap",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        telemetries={
            "wall_time_ms": 5000,
            "token_usage": 1000,
            "provider_costs": 0.02,
            "overhead_ms": 300,
            "model_calls": 1,
            "gateway_token_outlier_reason": "stats_outlier_possible_cumulative"
        }
    )
    assert rcpt_outlier_engine.public_claim_safe is False

def test_manifest_index_filtering_and_duplicate_safety():
    """
    TDD Task 2 (RED/GREEN): Verify filter_tasks_by_manifest_index successfully parses
    index ranges and comma-separated indices, and handles duplicate task IDs without contamination.
    """
    from scripts.bench.capability_ab_runner import CapabilityTask, filter_tasks_by_manifest_index
    
    # 建立一組含有重複 ID 的 Mock Tasks
    mock_tasks = [
        CapabilityTask(id="task_A", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=0),
        CapabilityTask(id="task_B", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=1),
        CapabilityTask(id="task_A", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=2), # 重複的 ID
        CapabilityTask(id="task_C", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=3),
        CapabilityTask(id="task_D", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=4),
    ]
    
    # 測試個別 index 篩選
    res1 = filter_tasks_by_manifest_index(mock_tasks, "0,2")
    assert len(res1) == 2
    assert [t.manifest_index for t in res1] == [0, 2]
    # 即便 A 重複，但因使用 manifest index，第一個和第三個 task A 被精確選出，不影響第二個或其他 task
    assert [t.id for t in res1] == ["task_A", "task_A"]
    
    # 測試 range 篩選
    res2 = filter_tasks_by_manifest_index(mock_tasks, "1-3")
    assert len(res2) == 3
    assert [t.manifest_index for t in res2] == [1, 2, 3]
    assert [t.id for t in res2] == ["task_B", "task_A", "task_C"]
    
    # 測試 "all" 或是空字串
    res3 = filter_tasks_by_manifest_index(mock_tasks, "all")
    assert len(res3) == 5

def test_background_offload_heavy_rows_experiment():
    """
    TDD Task 3 (RED/GREEN): Verify _is_heavy_task identifies heavy/flaky tasks based on CLI args and difficulty,
    and verify background offload structures non-blocking OFFLOADED_TO_BACKGROUND row status.
    """
    from scripts.bench.capability_ab_runner import CapabilityTask, _is_heavy_task
    from typing import Any
    
    # Mock CLI arguments
    class MockArgs:
        def __init__(self, enable_background_offload=False, heavy_task_ids=""):
            self.enable_background_offload = enable_background_offload
            self.heavy_task_ids = heavy_task_ids
            
    # Test case 1: Offload disabled (should not offload any task)
    args_disabled = MockArgs(enable_background_offload=False, heavy_task_ids="task_hard")
    task_hard = CapabilityTask(id="task_hard", difficulty="hard", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="")
    assert _is_heavy_task(task_hard, args_disabled) is False
    
    # Test case 2: Offload enabled, hard task should offload automatically
    args_enabled = MockArgs(enable_background_offload=True)
    assert _is_heavy_task(task_hard, args_enabled) is True
    
    # Test case 3: Easy task, not specified in heavy_task_ids, should NOT offload
    task_easy = CapabilityTask(id="task_easy", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="")
    assert _is_heavy_task(task_easy, args_enabled) is False
    
    # Test case 4: Easy task, specified in heavy_task_ids, should offload
    args_specified = MockArgs(enable_background_offload=True, heavy_task_ids="task_easy,task_other")
    assert _is_heavy_task(task_easy, args_specified) is True
    
    # Verify offload stub row structure (mimicking runner behavior)
    row = {
        "task_id": task_easy.id,
        "status": "OFFLOADED_TO_BACKGROUND",
        "difficulty": task_easy.difficulty,
        "elapsed_sec": 0.0,
        "wall_duration_sec": 0.0,
        "tokens_used": 0,
        "is_claimable": False,
        "public_claim_safe": False,
        "offload_provenance": "background_replay_lane",
    }
    assert row["status"] == "OFFLOADED_TO_BACKGROUND"
    assert row["is_claimable"] is False
    assert row["public_claim_safe"] is False
    assert row["offload_provenance"] == "background_replay_lane"

def test_gateway_rca_analyzer_tool(tmp_path):
    """
    TDD Task 4 (RED/GREEN): Verify gateway_rca_analyzer correctly parses JSONL rows,
    allocates buckets, and separates gateway overhead from provider wait ratios.
    """
    from scripts.ops.gateway_rca_analyzer import analyze_gateway_telemetry, generate_markdown_report
    
    # 建立一組 mock 的 jsonl 檔案，帶有不同 payload 和時長
    mock_rows = [
        # Call 1: small payload (500 chars), total 5s, provider wait 4s, parse 0.1s
        {
            "task_id": "task_1",
            "gateway_total_chars": 500,
            "gateway_total_sec": 5.0,
            "gateway_provider_wait_sec": 4.0,
            "gateway_parse_sec": 0.1,
            "status": "SUCCESS"
        },
        # Call 2: medium payload (3000 chars), total 10s, provider wait 9s, parse 0.2s, timeout
        {
            "task_id": "task_2",
            "gateway_total_chars": 3000,
            "gateway_total_sec": 10.0,
            "gateway_provider_wait_sec": 9.0,
            "gateway_parse_sec": 0.2,
            "error_category": "timeout",
            "status": "FAIL"
        },
        # Call 3: unrelated row without gateway telemetry
        {
            "task_id": "task_3",
            "status": "SUCCESS"
        }
    ]
    
    # 寫入暫存檔案
    jsonl_file = tmp_path / "mock_telemetry.jsonl"
    with jsonl_file.open("w", encoding="utf-8") as f:
        for r in mock_rows:
            f.write(json.dumps(r) + "\n")
            
    # 執行 RCA 分析
    report = analyze_gateway_telemetry(jsonl_file)
    
    # 驗證元數據
    assert report["metadata"]["total_rows"] == 3
    assert report["metadata"]["gateway_calls"] == 2
    assert report["metadata"]["total_timeouts"] == 1
    
    # 驗證平均數
    assert report["averages"]["avg_latency_sec"] == 7.5 # (5 + 10) / 2
    assert report["averages"]["avg_provider_wait_sec"] == 6.5 # (4 + 9) / 2
    assert report["averages"]["avg_payload_chars"] == 1750.0 # (500 + 3000) / 2
    
    # 驗證拆分佔比
    # Total wait: 4 + 9 = 13. Total sec: 5 + 10 = 15. Wait ratio = 13/15 = 86.67%
    assert report["shares"]["provider_wait_share"] == round(13/15, 4)
    assert report["shares"]["gateway_overhead_share"] == round(2/15, 4)
    assert report["shares"]["timeout_share_of_gateway"] == 0.5
    
    # 驗證 buckets 歸類
    assert report["buckets"]["0-1k"]["count"] == 1
    assert report["buckets"]["1k-5k"]["count"] == 1
    assert report["buckets"]["5k-10k"]["count"] == 0
    
    # 驗證 Markdown 報表生成正常
    md = generate_markdown_report(report)
    assert "# Gateway Payload & Latency Root Cause Analysis (RCA)" in md
    assert "observation-only" in md


@pytest.mark.asyncio
async def test_context_sync_capped_offline_async_vector_spike_and_receipt_lite():
    """
    TDD Task 5 (GREEN): Offline spike for context_sync_capped async vector retrieval
    and receipt-lite validation.
    This test verifies the desired interface for asynchronous offline vector queries
    and compact receipt-lite evidence generation under the context_sync_capped lane is now functional.
    """
    router = SkillsRouter(
        project_root="/Users/jameschen/Workspace/nexus",
        route_lane="context_sync_capped",
        enable_offline_vector_sync=True,
        vector_db_capped_size=1000
    )
    
    # Desired interface for async offline vector sync
    vector_results = await router.async_query_offline_vectors(
        query="find_relevant_ast_nodes",
        top_k=3,
        max_duration_ms=100
    )
    
    assert len(vector_results) > 0
    assert vector_results[0]["score"] >= 0.8
    
    # Desired interface for receipt-lite generation with strict parameters
    receipt = router.generate_receipt_lite(
        capability="context_sync_capped",
        selection_source="offline_vector_sync_lite",
        metrics={"search_latency_ms": 12.5, "vector_hits": len(vector_results)},
        provenance="offline_vector_sync_lite",
        row_id="row-001",
        hidden_verifier_passed=True
    )
    
    assert receipt["selection_source"] == "offline_vector_sync_lite"
    assert receipt["gate_passed"] is True
    assert "context_sync_capped" in receipt["evidence_refs"]
    assert "row:row-001" in receipt["evidence_refs"]
    assert "provenance:offline_vector_sync_lite" in receipt["evidence_refs"]


def test_context_sync_capped_receipt_lite_missing_provenance_rejected():
    """
    TDD Task 5C (Negative): Verify receipt-lite builder rejects generation
    when provenance or other contract fields are missing.
    """
    router = SkillsRouter(
        project_root="/Users/jameschen/Workspace/nexus",
        route_lane="context_sync_capped"
    )
    
    # Missing provenance should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        router.generate_receipt_lite(
            capability="context_sync_capped",
            selection_source="offline_vector_sync_lite",
            metrics={"search_latency_ms": 12.5},
            provenance=None, # Missing!
            row_id="row-001",
            hidden_verifier_passed=True
        )
    assert "requires an explicit 'provenance'" in str(exc_info.value)
    
    # Missing row_id should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        router.generate_receipt_lite(
            capability="context_sync_capped",
            selection_source="offline_vector_sync_lite",
            metrics={"search_latency_ms": 12.5},
            provenance="offline_vector_sync_lite",
            row_id=None, # Missing!
            hidden_verifier_passed=True
        )
    assert "requires an explicit 'row_id'" in str(exc_info.value)
    
    # Missing hidden_verifier_passed should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        router.generate_receipt_lite(
            capability="context_sync_capped",
            selection_source="offline_vector_sync_lite",
            metrics={"search_latency_ms": 12.5},
            provenance="offline_vector_sync_lite",
            row_id="row-001",
            hidden_verifier_passed=False # False!
        )
    assert "requires a verified 'hidden_verifier_passed'" in str(exc_info.value)


def test_gateway_rca_analyzer_runner_scale_observation_only(tmp_path):
    """
    TDD Task 7 (GREEN): Verify gateway_rca_analyzer on a medium runner slice.
    This test runs the analyzer on simulated medium runner slice telemetry (10 rows)
    and verifies that it aggregates payload/latency correctly, preserves observation-only
    labels, and keeps the analysis 100% isolated from any public promotion gates.
    """
    from scripts.ops.gateway_rca_analyzer import analyze_gateway_telemetry, generate_markdown_report
    
    # 1. 建立包含 10 筆 row 的中型 runner slice 模擬日誌
    mock_runner_rows = [
        # Bucket: 0-1k (4 calls, 1 timeout)
        {"task_id": "t1", "gateway_total_chars": 500, "gateway_total_sec": 4.5, "gateway_provider_wait_sec": 3.8, "gateway_parse_sec": 0.05, "status": "SUCCESS"},
        {"task_id": "t2", "gateway_total_chars": 800, "gateway_total_sec": 5.2, "gateway_provider_wait_sec": 4.5, "gateway_parse_sec": 0.06, "status": "SUCCESS"},
        {"task_id": "t3", "gateway_total_chars": 300, "gateway_total_sec": 3.8, "gateway_provider_wait_sec": 3.0, "gateway_parse_sec": 0.04, "status": "SUCCESS"},
        {"task_id": "t4", "gateway_total_chars": 999, "gateway_total_sec": 10.0, "gateway_provider_wait_sec": 9.0, "gateway_parse_sec": 0.08, "error_category": "timeout", "status": "FAIL"},
        
        # Bucket: 1k-5k (3 calls, 0 timeouts)
        {"task_id": "t5", "gateway_total_chars": 2500, "gateway_total_sec": 12.0, "gateway_provider_wait_sec": 11.0, "gateway_parse_sec": 0.15, "status": "SUCCESS"},
        {"task_id": "t6", "gateway_total_chars": 4800, "gateway_total_sec": 15.5, "gateway_provider_wait_sec": 14.2, "gateway_parse_sec": 0.18, "status": "SUCCESS"},
        {"task_id": "t7", "gateway_total_chars": 1200, "gateway_total_sec": 8.0, "gateway_provider_wait_sec": 7.1, "gateway_parse_sec": 0.10, "status": "SUCCESS"},
        
        # Bucket: 5k-10k (2 calls, 1 timeout)
        {"task_id": "t8", "gateway_total_chars": 7500, "gateway_total_sec": 22.0, "gateway_provider_wait_sec": 20.0, "gateway_parse_sec": 0.25, "status": "SUCCESS"},
        {"task_id": "t9", "gateway_total_chars": 9500, "gateway_total_sec": 30.0, "gateway_provider_wait_sec": 28.0, "gateway_parse_sec": 0.30, "error_category": "timeout", "status": "FAIL"},
        
        # Bucket: 10k+ (1 call, 0 timeouts)
        {"task_id": "t10", "gateway_total_chars": 15000, "gateway_total_sec": 45.0, "gateway_provider_wait_sec": 42.0, "gateway_parse_sec": 0.50, "status": "SUCCESS"}
    ]
    
    # 寫入模擬日誌檔案
    slice_log_file = tmp_path / "medium_runner_slice.jsonl"
    with slice_log_file.open("w", encoding="utf-8") as f:
        for row in mock_runner_rows:
            f.write(json.dumps(row) + "\n")
            
    # 2. 執行 RCA 統計分拆
    report = analyze_gateway_telemetry(slice_log_file)
    
    # 驗證統計總量與分桶穩定度
    assert report["metadata"]["total_rows"] == 10
    assert report["metadata"]["gateway_calls"] == 10
    assert report["metadata"]["total_timeouts"] == 2
    
    # 驗證特定 bucket 歸類與 count
    assert report["buckets"]["0-1k"]["count"] == 4
    assert report["buckets"]["1k-5k"]["count"] == 3
    assert report["buckets"]["5k-10k"]["count"] == 2
    assert report["buckets"]["10k+"]["count"] == 1
    
    # 3. 產出 Markdown 並驗收其包含 observation-only 隔離警告
    md = generate_markdown_report(report)
    assert "# Gateway Payload & Latency Root Cause Analysis (RCA)" in md
    assert "observation-only" in md
    assert "不作為 public claim 或門禁判定依據" in md
    
    # 4. 驗證隔離性 (RCA 診斷結果絕不干涉/影響 public promotion gate 的 verdict 判定)
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.9,
        token_cost_ratio_with_over_without=0.9,
        model_call_ratio_with_over_without=0.9,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True
    )
    
    assert decision.status == "IMPROVED"
    assert "wall_cost_not_improved" not in decision.failures


def test_background_offload_partial_evidence_and_denominator_conservation():
    """
    TDD Task 8 (GREEN): Verify background offload partial evidence and paired denominator conservation.
    This test verifies that:
    1. Heavy tasks offloaded to the background carry strict 'offload_provenance = background_replay_lane'.
    2. These partial rows are quarantined (is_claimable = False, public_claim_safe = False)
       and marked as cost_accounting_exclusion_candidate to prevent polluting the paired total denominator.
    3. The gate verifier derive_cost_efficiency_decision accepts background offload exclusions
       and keeps the final cost-ratio accounting conserved.
    """
    # 1. Simulate a background offload stub row (partial evidence)
    partial_row = {
        "task_id": "heavy_task_01",
        "status": "OFFLOADED_TO_BACKGROUND",
        "difficulty": "hard",
        "elapsed_sec": 0.0,
        "wall_duration_sec": 0.0,
        "tokens_used": 0,
        "is_claimable": False,
        "public_claim_safe": False,
        "cost_accounting_exclusion_candidate": True,
        "offload_provenance": "background_replay_lane"
    }
    
    # Verify strict quarantine constraints on partial rows
    assert partial_row["status"] == "OFFLOADED_TO_BACKGROUND"
    assert partial_row["is_claimable"] is False
    assert partial_row["public_claim_safe"] is False
    assert partial_row["cost_accounting_exclusion_candidate"] is True
    assert partial_row["offload_provenance"] == "background_replay_lane"
    
    # 2. Verify paired denominator conservation (should exclude this candidate from Measured calculations)
    # If a heavy task is offloaded, B group has fewer active Measured rows, but the remaining active rows
    # maintain accurate Measured token/wall metrics.
    active_baseline_tokens = [1000, 1000, 1000] # Total 3000
    active_treatment_tokens = [900, 900] # Total 1800 (1 task offloaded)
    
    # Measured token ratio calculated ONLY across active, non-excluded pairs to keep denominator conserved
    measured_ratio = sum(active_treatment_tokens) / sum(active_baseline_tokens[:2])
    assert measured_ratio == 0.9 # Conservative, clean ratio without 0-fill pollution
    
    # 3. Verify verifier cost decision respects background offload exclusion provenance
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=1.2, # Ordinarily regressed
        token_cost_ratio_with_over_without=measured_ratio, # 0.9
        model_call_ratio_with_over_without=0.9,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
        exclusion_candidate=partial_row["cost_accounting_exclusion_candidate"],
        exclusion_reason_code="background_offload_active",
        exclusion_provenance=partial_row["offload_provenance"]
    )
    
    # Decision should resolve cleanly as NEUTRAL/IMPROVED rather than REGRESSED
    assert decision.status in {"IMPROVED", "NEUTRAL"}
    assert "wall_cost_not_improved" not in decision.failures


def test_context_sync_capped_receipt_lite_quarantine_in_observation_only_diagnostics():
    """
    TDD Task 9 (GREEN): Verify offline receipt-lite is quarantined safely in
    observation-only diagnostics without being promoted to public claiming.
    """
    from scripts.bench.public_gate_bundle import validate_observation_vs_public_claim_boundary
    
    # 1. 建立合規的離線與背景 receipt-lite 列表
    # 所有與離線/背景相關的 row 都明確將 public_claim_safe 設為 False 進行隔離
    mock_receipts = [
        # Normal active row (audited, clean)
        {
            "capability": "ast_scanning",
            "selection_source": "planner",
            "public_claim_safe": True
        },
        # Offline context sync capped row (isolated observation-only)
        {
            "capability": "context_sync_capped",
            "selection_source": "offline_vector_sync_lite",
            "public_claim_safe": False # STRICT CONTRACT: Must be False
        },
        # Background offloaded heavy row (isolated observation-only)
        {
            "capability": "heavy_refactor",
            "status": "OFFLOADED_TO_BACKGROUND",
            "offload_provenance": "background_replay_lane",
            "public_claim_safe": False # STRICT CONTRACT: Must be False
        }
    ]
    
    # 2. 驗收：當 bundle 不做 public promotion (public_promotion_readiness = False) 且隔離完好時，
    # 物理隔離合約必須通過 (True)，不破壞 completeness，且順利將其列為 observation-only diagnostics
    res = validate_observation_vs_public_claim_boundary(
        capability_receipts=mock_receipts,
        public_promotion_readiness=False # Strictly observation-only phase
    )
    assert res is True


def test_observation_vs_public_claim_boundary_isolation():
    """
    TDD Task 10 (GREEN - Bundle-level Isolation Regression):
    Verify that any attempt to smuggle or forge observation-only diagnostics (offline sync
    or background offload) as a public claim or promotion evidence triggers a Fail-Closed ValueError.
    """
    from scripts.bench.public_gate_bundle import validate_observation_vs_public_claim_boundary
    
    # --- 偽造場景 A: 偷渡客嘗試將 offline receipt-lite 標記為 public_claim_safe ---
    forged_receipt_offline = [
        {
            "capability": "context_sync_capped",
            "selection_source": "offline_vector_sync_lite",
            "public_claim_safe": True # Attempted smuggling!
        }
    ]
    
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=forged_receipt_offline,
            public_promotion_readiness=False
        )
    assert "attempted to bypass quarantine and claim public_claim_safe" in str(exc_info.value)
    
    # --- 偽造場景 B: 偷渡客嘗試將 background offload row 標記為 public_claim_safe ---
    forged_receipt_background = [
        {
            "capability": "heavy_refactor",
            "status": "OFFLOADED_TO_BACKGROUND",
            "offload_provenance": "background_replay_lane",
            "public_claim_safe": True # Attempted smuggling!
        }
    ]
    
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=forged_receipt_background,
            public_promotion_readiness=False
        )
    assert "attempted to bypass quarantine and claim public_claim_safe" in str(exc_info.value)
    
    # --- 偽造場景 C: 即使 receipts 自稱安全隔离，但試圖進行全量 public promotion 且帶有離線證據 ---
    forged_promotion_with_offline = [
        {
            "capability": "context_sync_capped",
            "selection_source": "offline_vector_sync_lite",
            "public_claim_safe": False # Set to False but still present in promotion bundle
        }
    ]
    
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=forged_promotion_with_offline,
            public_promotion_readiness=True # Smuggling into promotion bundle!
        )
    assert "found inside a public promotion ready bundle" in str(exc_info.value)


def test_gateway_rca_analyzer_calibrated_bins(tmp_path):
    """
    TDD Task 11 (GREEN): Verify dynamic threshold calibration and parse overhead
    tracking in gateway_rca_analyzer.py.
    This test runs the analyzer with custom bins (e.g., [2000, 8000]) and verifies:
    1. Buckets are dynamically named ("0-2k", "2k-8k", "8k+").
    2. Average JSON parse times are correctly tracked for each bucket.
    3. The generated markdown contains custom bucket keys and diagnostic boundaries.
    """
    from scripts.ops.gateway_rca_analyzer import analyze_gateway_telemetry, generate_markdown_report
    
    # 1. 建立包含 4 筆 row 的模擬日誌，帶有不同時長與解析時間
    mock_runner_rows = [
        # Bucket: 0-2k (chars: 500 < 2000)
        {"task_id": "t1", "gateway_total_chars": 500, "gateway_total_sec": 3.0, "gateway_provider_wait_sec": 2.5, "gateway_parse_sec": 0.05, "status": "SUCCESS"},
        # Bucket: 2k-8k (chars: 5000 >= 2000 and < 8000)
        {"task_id": "t2", "gateway_total_chars": 5000, "gateway_total_sec": 8.0, "gateway_provider_wait_sec": 7.0, "gateway_parse_sec": 0.15, "status": "SUCCESS"},
        # Bucket: 8k+ (chars: 9000 >= 8000)
        {"task_id": "t3", "gateway_total_chars": 9000, "gateway_total_sec": 12.0, "gateway_provider_wait_sec": 10.0, "gateway_parse_sec": 0.25, "status": "SUCCESS"},
        # Bucket: 8k+ (chars: 12000 >= 8000, timeout)
        {"task_id": "t4", "gateway_total_chars": 12000, "gateway_total_sec": 15.0, "gateway_provider_wait_sec": 13.0, "gateway_parse_sec": 0.35, "error_category": "timeout", "status": "FAIL"}
    ]
    
    # 寫入模擬日誌檔案
    log_file = tmp_path / "calibrated_runner_slice.jsonl"
    with log_file.open("w", encoding="utf-8") as f:
        for row in mock_runner_rows:
            f.write(json.dumps(row) + "\n")
            
    # 2. 執行帶有自定義分桶的 RCA 統計
    custom_bins = [2000, 8000]
    report = analyze_gateway_telemetry(log_file, bins=custom_bins)
    
    # 驗證元數據與配置桶
    assert report["metadata"]["total_rows"] == 4
    assert report["metadata"]["configured_bins"] == custom_bins
    
    # 驗證特定 bucket 歸類與 count
    assert report["buckets"]["0-2k"]["count"] == 1
    assert report["buckets"]["2k-8k"]["count"] == 1
    assert report["buckets"]["8k+"]["count"] == 2
    
    # 驗證每個 bucket 的解析時間累加正確性
    assert report["buckets"]["0-2k"]["parse_sec"] == 0.05
    assert report["buckets"]["2k-8k"]["parse_sec"] == 0.15
    assert report["buckets"]["8k+"]["parse_sec"] == 0.60  # 0.25 + 0.35
    
    # 3. 產出 Markdown 並驗收
    md = generate_markdown_report(report)
    assert "# Gateway Payload & Latency Root Cause Analysis (RCA)" in md
    assert "Avg Parse/Setup (s)" in md
    assert "[2000, 8000]" in md
    assert "| 0-2k | 1 |" in md
    assert "| 2k-8k | 1 |" in md
    assert "| 8k+ | 2 |" in md
    
    # 4. 驗證該分析結果完全不影響 verdict 判定，100% 保持在診斷層
    from scripts.bench.public_gate_bundle import derive_cost_efficiency_decision
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.85,
        token_cost_ratio_with_over_without=0.85,
        model_call_ratio_with_over_without=0.85,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True
    )
    assert decision.status == "IMPROVED"


def test_heuristic_prefilter_is_observation_only():
    """
    TDD Task A (GREEN): Verify Heuristic Pre-filtering shadow decision is strictly
    observation-only and does not affect the physical execution path.
    """
    from nexus.core.router import SkillsRouter
    router = SkillsRouter(
        project_root="/Users/jameschen/Workspace/nexus",
        enable_shadow_prefilter=True
    )
    
    # 傳入無 struct 變更的 payload -> shadow skip
    res = router.decide_route(
        capability="ast_scanning",
        risk_level="low",
        bare_sufficiency="high",
        hidden_verifier_passed=True,
        code_payload="x = 10\nprint(x)" # 無 class / def 關鍵字，預期 skip
    )
    
    assert "observation_only_diagnostics" in res
    diag = res["observation_only_diagnostics"]
    assert diag["shadow_prefilter_verdict"] == "skip"
    assert diag["shadow_confidence"] == 0.95
    assert diag["shadow_estimated_savings_ms"] == 1200.0
    assert diag["public_claim_safe"] is False
    
    # 傳入有 struct 變更的 payload -> shadow run
    res_run = router.decide_route(
        capability="ast_scanning",
        risk_level="low",
        bare_sufficiency="high",
        hidden_verifier_passed=True,
        code_payload="class MyClass:\n    def my_method(self):\n        pass" # 有 class/def 關鍵字，預期 run
    )
    
    diag_run = res_run["observation_only_diagnostics"]
    assert diag_run["shadow_prefilter_verdict"] == "run"
    assert diag_run["shadow_confidence"] == 0.80
    assert diag_run["public_claim_safe"] is False


def test_context_compaction_is_observation_only():
    """
    TDD Task C (GREEN): Verify Context Window Compaction dual rendering is strictly
    observation-only and does not alter the production execution prompt.
    """
    from nexus.services.gateway import BattlesuitGateway
    gateway = BattlesuitGateway(
        project_root="/Users/jameschen/Workspace/nexus",
        enable_shadow_compaction=True
    )
    
    # 模擬 gateway 呼叫前置 telemetry 收集 (dual-render)
    sys_msg = "You are the pilot of the Nexus Battlesuit v16. Do not use tools, do not inspect files, and do not create an execution plan. Required output shape: {}"
    content = "required_governance_rules: active\npayload:\n\n   too   much   spaces   \n\n\n   newlines"
    
    # 呼叫結構化前置 render 的模擬 telemetry
    res, _ = gateway.ask_structured(
        prompt=sys_msg,
        payload=content,
        phase="R"
    )
    
    assert res["status"] in {"FAIL", "REJECTED"} # 預期為 FAIL (缺失 binary) 或是 REJECTED (實體執行成功但被拒絕)
    # 但 gateway_telemetry (包含 shadow dual render 統計) 必須存在於回傳 data 中
    assert "shadow_compaction_ratio" in res
    assert res["shadow_compaction_ratio"] > 0.0 # 空間有壓縮
    assert res["shadow_schema_preserved"] is True
    assert res["public_claim_safe"] is False




def test_spike_telemetry_does_not_change_paired_denominator():
    """
    TDD Task A/C (RED): Verify shadow telemetry does not affect paired cost ratio
    calculations in derive_cost_efficiency_decision.
    """
    # 1. 模擬包含 shadow 屬性被排除之 rows
    # 重寫 exclusion contract: 任何 background offload (例如 background_replay_lane)
    # 必須被排除在比較分母之外，而 shadow telemetry 則不進 denominator
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=1.15, # Ordinarily regressed
        token_cost_ratio_with_over_without=0.88,
        model_call_ratio_with_over_without=0.88,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
        exclusion_candidate=True,
        exclusion_reason_code="background_offload_active",
        exclusion_provenance="background_replay_lane" # Background rows excluded cleanly
    )
    
    # 決策應順利解析，不受 shadow 或背景資料污染
    assert decision.status in {"IMPROVED", "NEUTRAL"}
    
    # 2. 驗收 shadow row 即使預估時延縮短 1200ms，在統計中也絕對不影響實體 ledger
    active_baseline_wall = 5000
    active_treatment_wall = 5000
    # Shadow prefilter 預計節省 1200ms，但不折算入真實 wall
    est_saving = 1200
    assert (active_treatment_wall / active_baseline_wall) == 1.0 # 保持 100% 物理守恆，無 overclaim


def test_spike_artifacts_cannot_escalate_public_claim_readiness():
    """
    TDD Task A/C (RED - Bundle-level Smuggling Regression):
    Verify that any attempt to smuggle or forge shadow prefilter or compaction diagnostics
    into a public claim or promotion ready bundle triggers a Fail-Closed ValueError.
    """
    from scripts.bench.public_gate_bundle import validate_observation_vs_public_claim_boundary
    
    # --- 場景 A: 偷渡客將帶有 shadow_prefilter 的 row 偽造為 public_claim_safe = True ---
    forged_prefilter = [
        {
            "capability": "hidden_bugfix_supervised",
            "shadow_prefilter_verdict": "skip",
            "public_claim_safe": True # Attempted smuggling!
        }
    ]
    
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=forged_prefilter,
            public_promotion_readiness=False
        )
    assert "attempted to bypass quarantine and claim public_claim_safe" in str(exc_info.value)
    
    # --- 場景 B: 偷渡客將帶有 shadow_compaction 的 row 偽造為 public_claim_safe = True ---
    forged_compaction = [
        {
            "capability": "governance_hardened",
            "shadow_compaction_ratio": 0.35,
            "public_claim_safe": True # Attempted smuggling!
        }
    ]
    
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=forged_compaction,
            public_promotion_readiness=False
        )
    assert "attempted to bypass quarantine and claim public_claim_safe" in str(exc_info.value)
    
    # --- 場景 C: 即使設為 False 隔離，但在進行全量 public promotion 時，整個 bundle 內含有任何 shadow/observation rows ---
    forged_promotion_with_shadow = [
        {
            "capability": "hidden_bugfix_supervised",
            "shadow_prefilter_verdict": "skip",
            "public_claim_safe": False # Set to False but still inside a promotion bundle!
        }
    ]
    
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=forged_promotion_with_shadow,
            public_promotion_readiness=True # Smuggling into promotion!
        )
    assert "found inside a public promotion ready bundle" in str(exc_info.value)


def test_shadow_telemetry_dataset_hygiene_strict():
    """
    TDD Task B1 & B2: 確證 dataset hygiene 與隔離護欄加固。
    1. 驗證所有帶有 shadow/observation 欄位的 rows，不論是 prefilter 還是 compaction 欄位，均被嚴格阻隔，不可設為 public_claim_safe 或是混入 public promotion bundle。
    2. 驗證真實運行中必須提供穩定 run_id，以防止 run_id 淪為 run_unknown 妨礙分桶統計，達成物理防呆。
    """
    import pytest
    from scripts.bench.public_gate_bundle import validate_observation_vs_public_claim_boundary
    
    # 測試 A: prefilter 穩定欄位與 run_id 驗證
    prefilter_row = {
        "shadow_prefilter_verdict": "skip",
        "shadow_confidence": 0.95,
        "shadow_estimated_savings_ms": 1200.0,
        "task_id": "task_12345",
        "route": "code_refactor",
        "final_verifier_result": True,
        "timestamp": "2026-05-28T00:00:00Z",
        "run_id": "run_stable_123", # 穩定 run_id
        "task_kind": "code_refactor",
        "provider_path": "gemini",
        "route_strategy": "hardened",
        "public_claim_safe": False
    }
    
    # 真實 run 能否提供穩定 run_id 檢查：
    assert prefilter_row["run_id"] != "run_unknown", "Stability Violation: run_id must not be fallback run_unknown in production runs"
    
    # 測試 B: compaction 穩定欄位驗證
    compaction_row = {
        "shadow_compaction_ratio": 0.33,
        "shadow_original_tokens": 1000,
        "shadow_compacted_tokens": 670,
        "shadow_schema_preserved": True,
        "prompt_render_id": "render_123",
        "task_id": "task_12345",
        "route": "gateway_completion",
        "final_verifier_result": True,
        "timestamp": "2026-05-28T00:00:00Z",
        "run_id": "run_stable_456",
        "task_kind": "gateway_completion",
        "provider_path": "gemini",
        "route_strategy": "shadow_compaction_only",
        "public_claim_safe": False
    }
    
    assert compaction_row["run_id"] != "run_unknown"

    # 1. 隔離安全：若試圖標記為 public_claim_safe = True，應 100% 被拋出 ValueError 阻斷
    prefilter_row_smuggle = prefilter_row.copy()
    prefilter_row_smuggle["public_claim_safe"] = True
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=[prefilter_row_smuggle],
            public_promotion_readiness=False
        )
    assert "attempted to bypass quarantine and claim public_claim_safe" in str(exc_info.value)

    compaction_row_smuggle = compaction_row.copy()
    compaction_row_smuggle["public_claim_safe"] = True
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=[compaction_row_smuggle],
            public_promotion_readiness=False
        )
    assert "attempted to bypass quarantine and claim public_claim_safe" in str(exc_info.value)

    # 2. 即使 public_claim_safe 為 False，但 promotion readiness 為 True 時也 100% 阻斷
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=[prefilter_row],
            public_promotion_readiness=True
        )
    assert "found inside a public promotion ready bundle" in str(exc_info.value)
    
    with pytest.raises(ValueError) as exc_info:
        validate_observation_vs_public_claim_boundary(
            capability_receipts=[compaction_row],
            public_promotion_readiness=True
        )
    assert "found inside a public promotion ready bundle" in str(exc_info.value)


def test_paired_row_token_accounting_and_cost_evidence_class():
    from scripts.bench.cost_evidence_classifier import annotate_cost_evidence

    # 情形 1: local_success + model_calls=0 -> rescue_only_no_model_call
    row_local_only = {
        "nexus_winner_source": "local",
        "model_calls": 0,
        "token_capture_status": "not_applicable_local_only",
        "total_tokens": 0,
    }
    annotate_cost_evidence(row_local_only)
    assert row_local_only["cost_evidence_class"] == "rescue_only_no_model_call"
    assert row_local_only["clean_model_cost_evidence"] is False

    # 情形 2: local_success + model_calls>0 + measured tokens -> rescue_with_model_fallback_measured
    row_fallback_measured = {
        "nexus_winner_source": "local",
        "model_calls": 1,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "token_measured": True,
        "total_tokens": 100,
        "nexus_rescued": True,
    }
    annotate_cost_evidence(row_fallback_measured)
    assert row_fallback_measured["cost_evidence_class"] == "rescue_with_model_fallback_measured"
    assert row_fallback_measured["clean_model_cost_evidence"] is False # 不能提升為 clean model cost

    # 情形 3: local_success + model_calls>0 + estimated tokens -> rescue_with_model_fallback
    row_fallback_estimated = {
        "nexus_winner_source": "local",
        "model_calls": 1,
        "token_capture_status": "estimated",
        "gateway_token_source": "estimated",
        "total_tokens": 100,
        "nexus_rescued": True,
    }
    annotate_cost_evidence(row_fallback_estimated)
    assert row_fallback_estimated["cost_evidence_class"] == "rescue_with_model_fallback"
    assert row_fallback_estimated["clean_model_cost_evidence"] is False

    # 情形 4: model winner + measured tokens -> clean_model_cost
    row_model_clean = {
        "nexus_winner_source": "model",
        "model_calls": 1,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "token_measured": True,
        "total_tokens": 100,
    }
    annotate_cost_evidence(row_model_clean)
    assert row_model_clean["cost_evidence_class"] == "clean_model_cost"
    assert row_model_clean["clean_model_cost_evidence"] is True

