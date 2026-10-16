# Nexus Acceptance Check (Hardened)

- status: PASS
- gate_passed: true
- generated_at_utc: 2026-04-01T07:48:47.455375+00:00

## Criteria

- auto_repair_success_rate: PASS
  - window_rows: 5
  - opt_rows: 5
  - crystallize_samples: 0
  - success_rate: 100.0
  - threshold: 80.0
- phantom_false_positive_rate: PASS
  - recent_window_rows: 100
  - recent_false_positive_rate: 0.0
  - threshold: 3.0
- regression_and_side_effect: PASS
  - recent_window_rows: 100
  - recent_regression_pass_rate_avg: 100.0
  - regression_threshold: 95.0
- learning_promotion_gate: PASS
  - recent_window_rows: 100
  - recent_pattern_reuse_avg: 0.0
  - recent_next_run_hit_avg: 0.0
  - is_metric_passed: False
  - gate_mode: soft_signal
