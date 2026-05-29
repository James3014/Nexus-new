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
