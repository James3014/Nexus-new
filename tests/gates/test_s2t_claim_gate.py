from __future__ import annotations

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_strict import S2TStrictRuntimeGate, S2T3BAdvisor, robust_json_parse


def _candidate(candidate_id: str = "A", *, verifier_result: str = "pass") -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="repair_pass",
        content_ref=f".nexus/reports/s2t/{candidate_id}.json",
        selector_score=0.8,
        verifier_result=verifier_result,
        evidence_refs=[".nexus/reports/claim_gate.json"] if verifier_result == "pass" else [],
    )


def test_s2t_claim_gate_blocks_public_claim_without_gate_evidence() -> None:
    decision = S2TStrictRuntimeGate().evaluate(
        risk_tier="public_claim",
        candidates=[_candidate()],
        verifier_result="pass",
        verifier_evidence_ref="",
    )

    assert decision.passed is False
    assert decision.failure_reason == "public_claim_requires_gate_evidence"


def test_s2t_claim_gate_passes_verified_public_claim_with_evidence() -> None:
    decision = S2TStrictRuntimeGate().evaluate(
        risk_tier="public_claim",
        candidates=[_candidate()],
        verifier_result="pass",
        verifier_evidence_ref=".nexus/reports/claim_gate.json",
    )

    assert decision.passed is True
    assert decision.selected_candidate_id == "A"


def test_s2t_strict_gate_advisor_triggers_on_matching_canary(monkeypatch) -> None:
    import hashlib
    # 確保 mode 不為 off
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")
    
    triggered_task_id = ""
    for i in range(100):
        tid = f"test-task-{i}"
        h = int(hashlib.md5(tid.encode('utf-8')).hexdigest(), 16) % 100
        if h < 10:
            triggered_task_id = tid
            break
            
    assert triggered_task_id != ""
    
    gate = S2TStrictRuntimeGate(advisor=S2T3BAdvisor(force_simulation=True))

    decision = gate.evaluate(
        task_id=triggered_task_id,
        risk_tier="medium",
        candidates=[_candidate()],
        verifier_result="pass",
    )
    
    assert decision.advisor_used is True
    assert decision.advisor_selected_candidate_id == "A"
    assert decision.advisor_outcome_status == "active_advising"


def test_s2t_strict_gate_advisor_abstains_when_model_missing(tmp_path, monkeypatch) -> None:
    import hashlib
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")

    triggered_task_id = ""
    for i in range(100):
        tid = f"test-task-{i}"
        h = int(hashlib.md5(tid.encode('utf-8')).hexdigest(), 16) % 100
        if h < 10:
            triggered_task_id = tid
            break

    gate = S2TStrictRuntimeGate(
        advisor=S2T3BAdvisor(adapter_path=str(tmp_path / "missing-adapter")),
        evidence_log_path=tmp_path / "evidence.jsonl",
    )

    decision = gate.evaluate(
        task_id=triggered_task_id,
        risk_tier="medium",
        candidates=[_candidate()],
        verifier_result="pass",
    )

    assert decision.advisor_used is True
    assert decision.advisor_selected_candidate_id == ""
    assert decision.advisor_outcome_status.startswith("abstained: model_not_loaded")


def test_s2t_strict_gate_advisor_ignores_non_matching_canary() -> None:
    import hashlib
    ignored_task_id = ""
    for i in range(100):
        tid = f"test-task-{i}"
        h = int(hashlib.md5(tid.encode('utf-8')).hexdigest(), 16) % 100
        if h >= 10:
            ignored_task_id = tid
            break
            
    assert ignored_task_id != ""
    
    decision = S2TStrictRuntimeGate().evaluate(
        task_id=ignored_task_id,
        risk_tier="medium",
        candidates=[_candidate()],
        verifier_result="pass",
    )
    
    assert decision.advisor_used is False
    assert decision.advisor_selected_candidate_id == ""


def test_s2t_strict_gate_evidence_log_format(tmp_path, monkeypatch) -> None:
    import hashlib
    import json
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")

    # Find a task_id that matches the 10% canary
    triggered_task_id = ""
    for i in range(100):
        tid = f"test-task-{i}"
        h = int(hashlib.md5(tid.encode('utf-8')).hexdigest(), 16) % 100
        if h < 10:
            triggered_task_id = tid
            break
            
    assert triggered_task_id != ""
    
    log_file = tmp_path / "evidence.jsonl"
    gate = S2TStrictRuntimeGate(
        advisor=S2T3BAdvisor(force_simulation=True),
        evidence_log_path=log_file
    )
    
    decision = gate.evaluate(
        task_id=triggered_task_id,
        risk_tier="medium",
        candidates=[_candidate()],
        verifier_result="pass",
    )
    
    assert log_file.exists()
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    
    row = json.loads(lines[0])
    assert row["task_id"] == triggered_task_id
    assert row["risk_tier"] == "medium"
    assert row["baseline_selected_id"] == "A"
    assert row["advisor_selected_id"] == "A"
    assert row["advisor_parse_schema_verdict"] == "pass"
    assert row["verifier_result"] == "pass"
    assert row["trust_mismatch"] is False
    assert "timestamp_utc" in row
    assert row["advisor_status"] == "active_advising"


def test_robust_json_parse_various_formats() -> None:
    # 1. Standard JSON with null and true
    json_str = '{"selected_candidate_id": "cand-fail-33", "required_verifier": null, "valid": true}'
    res = robust_json_parse(json_str)
    assert res["selected_candidate_id"] == "cand-fail-33"
    assert res["required_verifier"] is None
    assert res["valid"] is True

    # 2. Standard Python Dict with single quotes and None/True
    py_dict_str = "{'selected_candidate_id': 'cand-fail-33', 'required_verifier': None, 'valid': True}"
    res = robust_json_parse(py_dict_str)
    assert res["selected_candidate_id"] == "cand-fail-33"
    assert res["required_verifier"] is None
    assert res["valid"] is True

    # 3. Mixed format (single quotes but null and true)
    mixed_str = "{'selected_candidate_id': 'cand-fail-33', 'required_verifier': null, 'valid': true}"
    res = robust_json_parse(mixed_str)
    assert res["selected_candidate_id"] == "cand-fail-33"
    assert res["required_verifier"] is None
    assert res["valid"] is True

    # 4. Dictionary containing "null", "None", "true", "True" as substring or string value
    boundary_str = "{'selected_candidate_id': 'cand-null-33', 'reason': 'annull', 'flag': 'None_id'}"
    res = robust_json_parse(boundary_str)
    assert res["selected_candidate_id"] == "cand-null-33"
    assert res["reason"] == "annull"
    assert res["flag"] == "None_id"


def test_s2t_advisor_provenance_lock(tmp_path) -> None:
    # 測試未註冊或不存在的 adapter_path，應該拋出錯誤並記錄為 provenance_lock_failed
    advisor = S2T3BAdvisor(adapter_path="training/adapters/non_existent_adapter_xyz")
    res = advisor.advise("medium", [])
    assert "abstain_reason" in res
    assert "provenance_lock_failed" in res["abstain_reason"]


def test_s2t_advisor_kill_switch(tmp_path, monkeypatch) -> None:
    # 測試當環境變數 NEXUS_S2T_3B_ADVISOR_ENABLED = "0" 時，S2TStrictRuntimeGate 應該正確跳過載入與模型推論
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_ENABLED", "0")
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")
    
    import hashlib
    import json
    triggered_task_id = ""
    for i in range(100):
        tid = f"killswitch-task-{i}"
        h = int(hashlib.md5(tid.encode('utf-8')).hexdigest(), 16) % 100
        if h < 10:
            triggered_task_id = tid
            break
            
    assert triggered_task_id != ""
    
    log_file = tmp_path / "killswitch_evidence.jsonl"
    gate = S2TStrictRuntimeGate(
        advisor=S2T3BAdvisor(force_simulation=False), # 不強制 simulation，預期會跑真實分支
        evidence_log_path=log_file
    )
    
    decision = gate.evaluate(
        task_id=triggered_task_id,
        risk_tier="medium",
        candidates=[_candidate()],
        verifier_result="pass",
    )
    
    # 1. 驗證決策未受影響，仍然由 baseline 正常產出
    assert decision.passed is True
    assert decision.selected_candidate_id == "A"
    
    # 2. 驗證 10% canary 遙測正常記錄為 advisor_disabled 且未加載模型
    # 注意：在新的 Rollout Control 中，若 ENABLED=0，advisor_used 會是 False
    assert decision.advisor_used is False
    assert decision.advisor_outcome_status == "not_run"


def test_s2t_strict_gate_advisor_forced_by_env(tmp_path, monkeypatch) -> None:
    # 測試當 NEXUS_S2T_3B_ADVISOR_FORCE = "1" 時，即使 task_id 不符合 10% canary 也要強制執行 advisor
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_FORCE", "1")
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")
    
    # 找一個不符合 10% canary 的 task_id
    import hashlib
    ignored_task_id = ""
    for i in range(100):
        tid = f"ignored-task-{i}"
        h = int(hashlib.md5(tid.encode('utf-8')).hexdigest(), 16) % 100
        if h >= 10:
            ignored_task_id = tid
            break
            
    assert ignored_task_id != ""
    
    log_file = tmp_path / "forced_evidence.jsonl"
    gate = S2TStrictRuntimeGate(
        advisor=S2T3BAdvisor(force_simulation=True),
        evidence_log_path=log_file
    )
    
    decision = gate.evaluate(
        task_id=ignored_task_id,
        risk_tier="medium",
        candidates=[_candidate()],
        verifier_result="pass",
    )
    
    # 即使 task_id 本應被 ignored，但因為 env_force 設為 1，所以 advisor 必須被使用
    assert decision.advisor_used is True
    assert decision.advisor_selected_candidate_id == "A"
    assert decision.advisor_outcome_status == "active_advising"


def test_s2t_strict_gate_advisor_rejects_failed_candidate(tmp_path, monkeypatch) -> None:
    # 測試當 advisor 推薦了 verifier_result = "fail" 的候選人時，Gate 必須進行過濾並拒絕該推薦，回退到 baseline 決策
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_FORCE", "1")
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")
    
    # 模擬 3B 模型返回選擇 "B" 候選人，而 "B" 是失敗的候選人
    class MockAdvisor(S2T3BAdvisor):
        def advise(self, risk_tier, candidates):
            return {
                "selected_candidate_id": "B",
                "selection_reason_codes": ["mock_test_fail"],
                "required_verifier": None,
                "abstain_reason": None
            }
            
    log_file = tmp_path / "semantic_fail_evidence.jsonl"
    gate = S2TStrictRuntimeGate(
        advisor=MockAdvisor(),
        evidence_log_path=log_file
    )
    
    candidates = [
        _candidate("A", verifier_result="pass"),
        _candidate("B", verifier_result="fail")
    ]
    
    decision = gate.evaluate(
        task_id="test-task-semantic-fail",
        risk_tier="medium",
        candidates=candidates,
        verifier_result="pass",
    )
    
    # 1. 驗證最終決策由 baseline 控制（選擇了 "A"），不受 "B" 影響
    assert decision.passed is True
    assert decision.selected_candidate_id == "A"
    
    # 2. 驗證 advisor 的推薦被過濾，決策置空，且狀態記錄為 advisor_semantic_rejected
    assert decision.advisor_used is True
    assert decision.advisor_selected_candidate_id == ""
    assert decision.advisor_outcome_status == "abstained: advisor_semantic_rejected"


def test_s2t_strict_gate_advisor_rejects_empty_evidence_candidate(tmp_path, monkeypatch) -> None:
    # 測試當 advisor 推薦了 evidence_refs 為空的候選人時，Gate 必須過濾該推薦
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_FORCE", "1")
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")
    
    class MockAdvisor(S2T3BAdvisor):
        def advise(self, risk_tier, candidates):
            return {
                "selected_candidate_id": "B",
                "selection_reason_codes": ["mock_test_empty_evidence"],
                "required_verifier": None,
                "abstain_reason": None
            }
            
    log_file = tmp_path / "empty_evidence_evidence.jsonl"
    gate = S2TStrictRuntimeGate(
        advisor=MockAdvisor(),
        evidence_log_path=log_file
    )
    
    # B 候選人其 evidence_refs 為空
    cand_b = S2TCandidate(
        candidate_id="B",
        source="repair_pass",
        content_ref="",
        selector_score=0.8,
        verifier_result="pass",
        evidence_refs=[]
    )
    
    candidates = [
        _candidate("A", verifier_result="pass"),
        cand_b
    ]
    
    decision = gate.evaluate(
        task_id="test-task-empty-evidence",
        risk_tier="medium",
        candidates=candidates,
        verifier_result="pass",
    )
    
    assert decision.selected_candidate_id == "A"
    assert decision.advisor_selected_candidate_id == ""
    assert decision.advisor_outcome_status == "abstained: advisor_semantic_rejected"



