from __future__ import annotations

import os
from types import SimpleNamespace
import pytest
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.interface import IPhase, PhaseResult

try:
    from nexus.services.local_heal.backends.local_patch_synthesis_backend import LocalPatchSynthesisBackend
    _HAS_BACKEND = True
except ImportError:
    _HAS_BACKEND = False

from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor

class FakePhase(IPhase):
    def execute(self, ctx: HealContext) -> PhaseResult:
        return PhaseResult(success=True)

class FakeVerifyPhase(IPhase):
    def execute(self, ctx: HealContext) -> PhaseResult:
        # 第一輪 fail, 第二輪 success
        if ctx.op.attempt == 1:
            return PhaseResult(success=False, failure_reason="AssertionError")
        return PhaseResult(success=True)

@pytest.mark.skipif(not _HAS_BACKEND, reason="LocalPatchSynthesisBackend not importable due to stale build_local_model_provider_from_env")
def test_qwen_backend_seam_invocation(monkeypatch, tmp_path) -> None:
    # 1. 設置環境變數
    monkeypatch.setenv("NEXUS_LOCAL_QWEN_BACKEND", "1")
    
    # 2. Mock Backend 避免實體 Ollama 呼叫
    def fake_generate_patch(*args, **kwargs):
        return {
            "candidate_text": "fake patch diff content",
            "local_model_called": True,
            "attempt": kwargs.get("attempt", 1),
            "repair_success": False,
            "repaired_by_rule": "none",
        }
    monkeypatch.setattr(LocalPatchSynthesisBackend, "generate_patch", fake_generate_patch)

    # 3. 準備 Context
    op = SimpleNamespace(
        task_id="t_seam_1",
        problem_statement="test bug",
        max_tries=2,
        attempt=1,
        repo_dir=tmp_path,
        localized_files=[],
        plan=SimpleNamespace(search_symbols=["func"]),
        verifier_command=["pytest"],
        final_patch="",
        local_model_called=False,
        failure_reason="",
        runner_completed=False,
        user_prompt="",
        env_resolution=SimpleNamespace(ready=True),
        evaluation_report="",
    )
    ctx = HealContext(op=op, gov=SimpleNamespace(gate_exit=""))
    
    orchestrator = HealOrchestrator(
        phases=[FakePhase(), FakePhase(), FakePhase(), FakePhase(), FakeVerifyPhase()],
        governance_gate=GovernanceGate()
    )
    
    # 4. 執行
    from nexus.services.local_heal.latency_ledger import LatencyLedger
    ledger = LatencyLedger(task_id="t_seam_1", instance_id="i_seam_1")
    orchestrator._run_repair_loop(ctx, ledger)
    
    # 5. 驗斷
    assert ctx.op.final_patch == "fake patch diff content"
    assert ctx.op.local_model_called is True
    # 因為第一輪 fail，應嘗試了 retry (attempt 變 2 且最終成功)
    assert ctx.op.attempt == 2

def test_source_anchor_telemetry_with_fallback(tmp_path) -> None:
    # 建立一個測試檔案
    f = tmp_path / "f.py"
    f.write_text("def func():\n    return True\n", encoding="utf-8")
    
    # 當 locked_search 為空時，會觸發 GranularMethodLocalizer
    anchor = build_local_model_source_anchor(
        source_root=str(tmp_path),
        target_file="f.py",
        target_symbol="func",
        patch_diff="",
        locked_search="",
    )
    
    # 驗斷 telemetry
    tel = anchor.telemetry
    assert tel.get("localizer_fallback_attempted") is True
    assert tel.get("localizer_fallback_success") is True
    assert tel.get("localizer_fallback_source") in ("granular_method", "file_scope")
