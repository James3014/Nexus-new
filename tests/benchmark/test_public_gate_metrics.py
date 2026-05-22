from scripts.bench.public_gate_metrics import (
    mean_number,
    median,
    paired_metric_ratios,
    paired_prompt_purity_ratios,
    safe_ratio,
)


def test_mean_number_falls_back_only_when_metric_is_empty():
    rows = [
        {"wall_duration_sec": "", "duration_sec": 2.0},
        {"wall_duration_sec": 4.0, "duration_sec": 99.0},
        {"wall_duration_sec": "bad", "duration_sec": 6.0},
    ]

    assert mean_number(rows, "wall_duration_sec", "duration_sec") == 3.0


def test_safe_ratio_and_median_keep_public_gate_rounding():
    assert safe_ratio(1, 3) == 0.3333
    assert safe_ratio(1, 0) == 0.0
    assert median([3.0, 1.0, 2.0]) == 2.0
    assert median([1.0, 3.0]) == 2.0


def test_paired_metric_ratios_match_rows_by_task_and_trial():
    with_rows = [
        {"task_id": "a", "trial_index": 1, "wall_duration_sec": 2.0},
        {"task_id": "b", "trial_index": 1, "wall_duration_sec": 3.0},
    ]
    without_rows = [
        {"task_id": "a", "trial_index": 1, "wall_duration_sec": 4.0},
        {"task_id": "missing", "trial_index": 1, "wall_duration_sec": 9.0},
        {"task_id": "b", "trial_index": 1, "wall_duration_sec": 0.0},
    ]

    assert paired_metric_ratios(with_rows, without_rows, "wall_duration_sec") == [0.5]


def test_paired_prompt_purity_ratios_prefer_explicit_index_then_prompt_chars():
    with_rows = [
        {"task_id": "explicit", "trial_index": 1, "prompt_purity_index": 1.01, "gateway_prompt_chars": 99},
        {"task_id": "derived", "trial_index": 1, "gateway_prompt_chars": 40},
        {"task_id": "missing_without", "trial_index": 1, "gateway_prompt_chars": 10},
    ]
    without_rows = [
        {"task_id": "explicit", "trial_index": 1, "gateway_prompt_chars": 10},
        {"task_id": "derived", "trial_index": 1, "gateway_prompt_chars": 80},
        {"task_id": "zero", "trial_index": 1, "gateway_prompt_chars": 0},
    ]

    assert paired_prompt_purity_ratios(with_rows, without_rows) == [1.01, 0.5]
