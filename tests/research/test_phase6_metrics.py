from nexus.research.phase6 import Phase6Metrics
from nexus.research.phase6 import compute_phase6_metrics
from nexus.research.phase6 import gate_passed


def test_compute_phase6_metrics_uses_last20_window() -> None:
    rows = []
    for _ in range(80):
        rows.append({"mismatch_rate": 2.0, "proof_ratio": 80.0, "best_precision": 0.7})
    for _ in range(20):
        rows.append({"mismatch_rate": 0.3, "proof_ratio": 97.0, "best_precision": 0.99})

    metrics = compute_phase6_metrics(rows)

    assert metrics.mismatch_lt_0_5_last20 == 20
    assert metrics.mismatch_max_last20 == 0.3
    assert metrics.proof_ratio_min_last20 == 97.0
    assert metrics.best_precision == 0.99


def test_gate_passed_requires_all_conditions() -> None:
    assert gate_passed(
        Phase6Metrics(
            mismatch_lt_0_5_last20=20,
            mismatch_max_last20=0.49,
            proof_ratio_min_last20=95.0,
            best_precision=0.99,
        )
    )
    assert not gate_passed(
        Phase6Metrics(
            mismatch_lt_0_5_last20=19,
            mismatch_max_last20=0.49,
            proof_ratio_min_last20=95.0,
            best_precision=0.99,
        )
    )

