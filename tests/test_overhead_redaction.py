from __future__ import annotations

import pytest
from nexus.core.cost_evidence_contracts import calculate_adjusted_overhead

def test_calculate_adjusted_overhead_redaction():
    # 斷言在 200ms raw overhead 時經過 redaction 後 adjusted overhead 應為 50ms (預設扣除 150ms)
    assert calculate_adjusted_overhead(200.0) == 50.0
    # 斷言扣除後若低於 0 則應為 0.0
    assert calculate_adjusted_overhead(100.0) == 0.0
    # 測試自訂扣除開銷
    assert calculate_adjusted_overhead(200.0, runner_ast_parser_overhead_ms=100.0) == 100.0


def test_derive_cost_evidence_class_commercial_downgrade():
    from nexus.core.cost_evidence_contracts import CostEvidenceClass, derive_cost_evidence_class
    
    # 正常 clean model cost 的情況，但傳入 token_cost_ratio = 1.3
    # 預期會因為超出 1.2 的商業門檻，自動降級為 TOKEN_UNRELIABLE
    result = derive_cost_evidence_class(
        model_calls=1,
        provider_token_measured=True,
        token_reliable=True,
        runner_overhead_polluted=False,
        local_success=False,
        token_cost_ratio=1.3
    )
    assert result == CostEvidenceClass.TOKEN_UNRELIABLE

    # 若在門檻內 (如 1.1)，應保持 CLEAN_MODEL_COST
    result_ok = derive_cost_evidence_class(
        model_calls=1,
        provider_token_measured=True,
        token_reliable=True,
        runner_overhead_polluted=False,
        local_success=False,
        token_cost_ratio=1.1
    )
    assert result_ok == CostEvidenceClass.CLEAN_MODEL_COST

