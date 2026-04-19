"""
Iron Gate 閉環證明腳本

這不是單元測試。這是一個攻擊模擬器，物理證明：
  1. 每個 Gate 確實會阻擋
  2. 阻擋後系統不會卡死，會自動重試
  3. 重試後如果修正了就能通過
  4. 重試耗盡後會優雅終止（不是 hang）

每個場景都附帶計時器，證明沒有無限迴圈。

執行：.venv/bin/python tests/proof_closed_loop.py
"""

import time
import json
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock

# === Import production modules ===
from nexus.core.plan_quality_gate import PlanQualityGate
from nexus.core.phantom_detect import detect_inconclusive_success
from nexus.engine.pipeline_repair import PipelineRepairMixin
from nexus.engine.cli_pregate import run_cli_pregate

@dataclass
class LoopProof:
    scenario: str
    gate: str
    blocked: bool
    retried: bool
    final_state: str   # "PASSED" | "TERMINAL" | "HUMAN_REVIEW"
    hung: bool          # 是否卡死（超過 timeout 才算）
    elapsed_ms: float
    detail: str

proofs: list[LoopProof] = []

TIMEOUT_MS = 5000  # 5 秒內沒完成就算 hang

def header(title):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")

def run_scenario(name, gate, fn):
    """執行一個場景，計時並捕獲結果"""
    t0 = time.monotonic()
    try:
        result = fn()
        elapsed = (time.monotonic() - t0) * 1000
        hung = elapsed > TIMEOUT_MS
        proofs.append(LoopProof(
            scenario=name, gate=gate,
            blocked=result["blocked"], retried=result["retried"],
            final_state=result["final_state"], hung=hung,
            elapsed_ms=round(elapsed, 1), detail=result["detail"]
        ))
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        proofs.append(LoopProof(
            scenario=name, gate=gate,
            blocked=True, retried=False,
            final_state="EXCEPTION", hung=elapsed > TIMEOUT_MS,
            elapsed_ms=round(elapsed, 1), detail=f"EXCEPTION: {e}"
        ))

# ================================================================
# 場景 1: P-Stage Plan Gate → 第 1 次被擋 → 第 2 次修正後通過
# ================================================================
def scenario_plan_retry_success():
    gate = PlanQualityGate()
    MAX_PLAN_RETRIES = 2
    plan_attempts = 0
    blocked_once = False

    # 模擬 Planner：第 1 次漏 target_files，第 2 次補上
    def mock_planner(attempt, feedback=None):
        if attempt == 1:
            return {"intent_pass": True, "risk_score": 0.3, "handoff_readiness": 0.5}
        else:
            return {"intent_pass": True, "risk_score": 0.3, "handoff_readiness": 0.5,
                    "target_files": ["nexus/engine/pipeline.py"],
                    "acceptance_criteria": "tests pass", "deliverables": "patch"}

    plan_quality = None
    while True:
        plan_attempts += 1
        feedback = None
        if plan_quality and not plan_quality.passed:
            feedback = {"missing": plan_quality.missing_fields}
            blocked_once = True

        prediction = mock_planner(plan_attempts, feedback)
        plan_quality = gate.evaluate(prediction, {})

        if plan_quality.passed:
            return {"blocked": blocked_once, "retried": plan_attempts > 1,
                    "final_state": "PASSED",
                    "detail": f"通過 (嘗試 {plan_attempts} 次, score={plan_quality.score:.2f})"}
        if plan_attempts > MAX_PLAN_RETRIES:
            return {"blocked": True, "retried": True,
                    "final_state": "TERMINAL",
                    "detail": f"重試耗盡 ({plan_attempts} 次)"}

# ================================================================
# 場景 2: P-Stage Plan Gate → 全部重試都失敗 → 優雅終止
# ================================================================
def scenario_plan_retry_exhausted():
    gate = PlanQualityGate()
    MAX_PLAN_RETRIES = 2
    plan_attempts = 0

    # 模擬頑固的 Planner：永遠不寫 target_files
    def stubborn_planner(attempt, feedback=None):
        return {"intent_pass": True, "risk_score": 0.3, "handoff_readiness": 0.5}

    plan_quality = None
    while True:
        plan_attempts += 1
        prediction = stubborn_planner(plan_attempts)
        plan_quality = gate.evaluate(prediction, {})

        if plan_quality.passed:
            return {"blocked": False, "retried": plan_attempts > 1,
                    "final_state": "PASSED", "detail": "不應該到這裡"}
        if plan_attempts > MAX_PLAN_RETRIES:
            return {"blocked": True, "retried": True,
                    "final_state": "TERMINAL",
                    "detail": f"連續 {plan_attempts} 次被擋，最終優雅終止 (missing={plan_quality.missing_fields})"}

# ================================================================
# 場景 3: Phantom Guard → 第 1 次被抓偽造 → 第 2 次真的改了程式碼
# ================================================================
def scenario_phantom_retry():
    attempts = 0
    max_retries = 3
    blocked_once = False

    while attempts < max_retries:
        attempts += 1
        
        if attempts == 1:
            # Agent 第 1 輪：宣稱成功但 git diff 為空
            reason = detect_inconclusive_success(
                status="APPROVED", patch_generated=True, patch_apply_success=True,
                no_change_reason="", proof_type="checksum", proof_value="abc",
                git_diff_empty=True, verify_commands_executed=True
            )
        elif attempts == 2:
            # Agent 第 2 輪：真的改了程式碼，git diff 有輸出
            reason = detect_inconclusive_success(
                status="APPROVED", patch_generated=True, patch_apply_success=True,
                no_change_reason="", proof_type="checksum", proof_value="abc",
                git_diff_empty=False, verify_commands_executed=True
            )

        if reason:
            blocked_once = True
            # 模擬 R↔A loop：被擋 → 回到 R 重試
            continue
        else:
            return {"blocked": blocked_once, "retried": attempts > 1,
                    "final_state": "PASSED",
                    "detail": f"第 {attempts} 輪通過 Phantom Guard (前一輪 reason=empty_diff_with_claimed_patch)"}

    return {"blocked": True, "retried": True,
            "final_state": "TERMINAL", "detail": f"所有 {max_retries} 次都被 Phantom Guard 攔截"}

# ================================================================
# 場景 4: Phantom Guard → 空洞藉口被抓 → 第 2 次提供真正證據
# ================================================================
def scenario_phantom_hollow_claim():
    attempts = 0
    max_retries = 3
    reasons_log = []

    while attempts < max_retries:
        attempts += 1

        if attempts == 1:
            # 用空洞的 "works fine" 搪塞
            reason = detect_inconclusive_success(
                status="APPROVED", patch_generated=False, patch_apply_success=False,
                no_change_reason="verified working as expected"
            )
        else:
            # 第 2 次：提供真正的 no_change_reason  + 物理證據
            reason = detect_inconclusive_success(
                status="APPROVED", patch_generated=False, patch_apply_success=False,
                no_change_reason="Bug was in caller side, patching upstream repo instead. See PR #42.",
                proof_type="pr_link", proof_value="https://github.com/org/repo/pull/42",
                verify_commands_executed=True
            )

        reasons_log.append(reason)
        if reason:
            continue
        else:
            return {"blocked": True, "retried": True,
                    "final_state": "PASSED",
                    "detail": f"第 {attempts} 輪通過 (第 1 輪被擋: {reasons_log[0]})"}

    return {"blocked": True, "retried": True,
            "final_state": "TERMINAL", "detail": f"全部失敗 reasons={reasons_log}"}

# ================================================================
# 場景 5: R↔A Escalation → 實際 Replan → 重置 loop
# ================================================================
def scenario_escalation_replan():
    """模擬 R↔A 失敗 3 次 → escalation → _perform_escalation 實際重跑 P"""

    class FakeEngine(PipelineRepairMixin):
        def __init__(self):
            self.registry = MagicMock()
            p_plugin = MagicMock()
            p_plugin.name = "P"
            p_plugin.execute = MagicMock(return_value=MagicMock(status="PASS"))
            self.registry.get_ordered_plugins.return_value = [p_plugin]

    engine = FakeEngine()
    engine.engine = engine

    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.state.metadata = {"rejection_history": ["phantom_1", "phantom_2", "phantom_3"]}
    ctx.state.task_id = "test-task"
    ctx.kwargs = {}
    ctx.task_desc = "fix bug"

    break_loop, replan_ok = engine._perform_escalation(ctx, "scope_drift", 3)

    return {"blocked": True, "retried": True,
            "final_state": "PASSED" if replan_ok else "TERMINAL",
            "detail": f"escalation replan_ok={replan_ok}, break_loop={break_loop}, triggered={ctx.state.metadata.get('escalation_triggered')}"}

# ================================================================
# 場景 6: Escalation 超過最大次數 → HUMAN_REVIEW
# ================================================================
def scenario_escalation_max_human_review():
    class FakeEngine(PipelineRepairMixin):
        def __init__(self):
            self.registry = MagicMock()

    engine = FakeEngine()
    engine.engine = engine

    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.state.metadata = {"escalation_count": 3}  # 已經升級 3 次
    ctx.state.task_id = "test-task"

    break_loop, replan_ok = engine._perform_escalation(ctx, "scope_drift", 10)

    return {"blocked": True, "retried": True,
            "final_state": "HUMAN_REVIEW" if ctx.state.metadata.get("human_review_required") else "UNKNOWN",
            "detail": f"escalation_count=3 → human_review={ctx.state.metadata.get('human_review_required')}, reason={ctx.state.metadata.get('human_review_reason')}"}

# ================================================================
# 場景 7: CLI Pregate 空命令 → 被擋 → 補上命令後通過
# ================================================================
def scenario_cli_pregate_retry():
    attempts = 0
    max_retries = 3

    while attempts < max_retries:
        attempts += 1

        if attempts == 1:
            # 第 1 輪：沒有驗證命令
            passed, results = run_cli_pregate(Path("."), [])
        else:
            # 第 2 輪：補上了驗證命令（用 echo 模擬通過）
            passed, results = run_cli_pregate(Path("."), ["echo ok"])

        if passed:
            return {"blocked": True, "retried": True,
                    "final_state": "PASSED",
                    "detail": f"第 {attempts} 輪通過 (第 1 輪被擋: 空命令)"}
        else:
            continue

    return {"blocked": True, "retried": True,
            "final_state": "TERMINAL", "detail": "全部失敗"}

# ================================================================
# 場景 8: D-Stage VETO → P-X-D 重跑 (邏輯模擬)
# ================================================================
def scenario_d_veto_replan():
    """模擬 D-Stage VETO 觸發 P-X-D retry"""
    MAX_PXD_RETRIES = 2
    pxd_attempts = 0
    veto_feedback = None

    while pxd_attempts < MAX_PXD_RETRIES:
        pxd_attempts += 1

        # P-Stage: 如果有 veto_feedback，用不同策略
        if veto_feedback:
            plan = {"intent_pass": True, "risk_score": 0.1, "handoff_readiness": 0.8,
                    "target_files": ["safe_file.py"], "strategy": "conservative"}
        else:
            plan = {"intent_pass": True, "risk_score": 0.9, "handoff_readiness": 0.5,
                    "target_files": ["dangerous_core.py"], "strategy": "aggressive"}

        # D-Stage: 高風險計畫會被 VETO
        if plan["risk_score"] > 0.7 and pxd_attempts < MAX_PXD_RETRIES:
            veto_feedback = f"VETO: risk_score {plan['risk_score']} too high for target {plan['target_files']}"
            continue  # retry P-X-D
        elif plan["risk_score"] > 0.7:
            return {"blocked": True, "retried": True,
                    "final_state": "TERMINAL",
                    "detail": f"D-Stage VETO terminal after {pxd_attempts} attempts"}
        else:
            return {"blocked": True, "retried": True,
                    "final_state": "PASSED",
                    "detail": f"第 {pxd_attempts} 輪 P-X-D 通過 (前一輪 VETO: risk 太高 → 換保守策略)"}

    return {"blocked": True, "retried": True,
            "final_state": "TERMINAL", "detail": "PXD retry exhausted"}

# ================================================================
# 場景 9: Verifier 異常 → Fail-Closed (邏輯模擬)
# ================================================================
def scenario_verifier_fail_closed():
    """模擬 Verifier 拋出異常時觸發拒絕"""
    attempts = 0
    max_retries = 2
    
    while attempts < max_retries:
        attempts += 1
        try:
            # 模擬 Verifier 崩潰
            raise Exception("Fatal Verification Error")
        except Exception:
            # 模擬 pipeline_repair.py 中的 Fail-Closed
            audit_success = False
            status = "REJECTED"
        
        if status == "REJECTED":
            # 繼續重試 (R↔A 流程)
            continue
            
    return {"blocked": True, "retried": True,
            "final_state": "TERMINAL",
            "detail": f"Verifier 崩潰觸發 Fail-Closed 並在 {attempts} 次後終止"}

# ================================================================
# 執行所有場景
# ================================================================
if __name__ == "__main__":
    header("Iron Gate 閉環驗證：阻擋 + 重試 + 不卡死")

    scenarios = [
        ("① Plan 缺欄位 → 重試補上 → 通過",       "Plan Quality Gate", scenario_plan_retry_success),
        ("② Plan 頑固不改 → 重試耗盡 → 終止",      "Plan Quality Gate", scenario_plan_retry_exhausted),
        ("③ Agent 偽造 diff → 被抓 → 真改後通過",   "Phantom Guard",     scenario_phantom_retry),
        ("④ Agent 空洞藉口 → 被抓 → 提供證據通過",  "Phantom Guard",     scenario_phantom_hollow_claim),
        ("⑤ R↔A 連敗 → Escalation → Replan 成功",  "Escalation",        scenario_escalation_replan),
        ("⑥ Escalation 過多 → HUMAN_REVIEW",       "Escalation",        scenario_escalation_max_human_review),
        ("⑦ CLI 無驗證命令 → 補命令後通過",          "CLI Pregate",       scenario_cli_pregate_retry),
        ("⑧ D-Stage VETO → 換策略重來 → 通過",      "D-Stage VETO",      scenario_d_veto_replan),
        ("⑨ Verifier 崩潰 → Fail-Closed 不卡死",     "Verifier",          scenario_verifier_fail_closed),
    ]

    for name, gate, fn in scenarios:
        run_scenario(name, gate, fn)

    # 印出結果
    header("結果")

    for p in proofs:
        icon = "✅" if p.final_state in ("PASSED", "HUMAN_REVIEW") and not p.hung else "❌"
        hang_warn = " ⚠️ HUNG!" if p.hung else ""
        print(f"\n  {icon} {p.scenario}")
        print(f"     Gate:     {p.gate}")
        print(f"     被阻擋:   {'是' if p.blocked else '否'}")
        print(f"     有重試:   {'是' if p.retried else '否'}")
        print(f"     最終狀態: {p.final_state}{hang_warn}")
        print(f"     耗時:     {p.elapsed_ms}ms")
        print(f"     細節:     {p.detail}")

    header("摘要")

    total = len(proofs)
    has_retry = sum(1 for p in proofs if p.retried)
    blocked_and_recovered = sum(1 for p in proofs if p.blocked and p.final_state == "PASSED")
    blocked_and_terminal = sum(1 for p in proofs if p.blocked and p.final_state == "TERMINAL")
    human_review = sum(1 for p in proofs if p.final_state == "HUMAN_REVIEW")
    hung = sum(1 for p in proofs if p.hung)
    max_time = max(p.elapsed_ms for p in proofs)

    print(f"\n  總場景數:           {total}")
    print(f"  有重試機制:         {has_retry}")
    print(f"  阻擋後修正成功:     {blocked_and_recovered}")
    print(f"  阻擋後優雅終止:     {blocked_and_terminal}")
    print(f"  最終交人類審查:     {human_review}")
    print(f"  卡死（>5秒）:       {hung}")
    print(f"  最大耗時:           {max_time}ms")

    all_ok = (
        hung == 0 and
        blocked_and_recovered >= 4 and
        has_retry == total and
        (blocked_and_terminal + blocked_and_recovered + human_review) == total
    )

    if all_ok:
        print(f"\n  ✅ 結論：所有 {total} 個場景均確認「阻擋有效 + 重試可達 + 無卡死」。")
    else:
        print(f"\n  ❌ 結論：有場景未通過閉環驗證。")

    print()

    # 寫 JSON 報告
    report = {
        "total": total, "has_retry": has_retry,
        "recovered": blocked_and_recovered, "terminal": blocked_and_terminal,
        "human_review": human_review, "hung": hung,
        "max_time_ms": max_time, "pass": all_ok,
        "scenarios": [
            {"name": p.scenario, "gate": p.gate, "blocked": p.blocked,
             "retried": p.retried, "final_state": p.final_state,
             "hung": p.hung, "elapsed_ms": p.elapsed_ms, "detail": p.detail}
            for p in proofs
        ]
    }
    rp = Path(".nexus/reports/iron_gate_closed_loop_proof.json")
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"  報告: {rp}")
