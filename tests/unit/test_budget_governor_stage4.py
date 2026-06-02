import pytest
from nexus.engine.budget_governor import BudgetGovernor, BudgetPressure, HistoryMode

def test_budget_governor_pressure_calculation():
    gov = BudgetGovernor()
    # High tokens should trigger high pressure
    assert gov.calculate_pressure(current_rounds=5, current_tokens=80000) == BudgetPressure.HIGH
    # High rounds should trigger critical pressure
    assert gov.calculate_pressure(current_rounds=14, current_tokens=10000, max_rounds=15) == BudgetPressure.CRITICAL
    # Low usage
    assert gov.calculate_pressure(current_rounds=1, current_tokens=5000) == BudgetPressure.LOW

def test_compaction_strategy_critical():
    gov = BudgetGovernor()
    strategy = gov.determine_compaction_strategy(BudgetPressure.CRITICAL)
    assert strategy["history_mode"] == HistoryMode.DROPPED
    assert strategy["decomposition_required"] is True

def test_compaction_receipt_generation():
    gov = BudgetGovernor()
    receipt = gov.emit_compaction_receipt(
        task_id="t-1",
        prev_len=1000,
        curr_len=400,
        mode=HistoryMode.SUMMARIZED,
        reasons=["token_limit_exceeded"]
    )
    assert receipt.compression_ratio == 0.6
    assert receipt.history_mode == HistoryMode.SUMMARIZED
    assert "token_limit_exceeded" in receipt.compaction_reason_codes
