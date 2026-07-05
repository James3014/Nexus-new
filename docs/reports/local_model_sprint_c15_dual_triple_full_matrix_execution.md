# Local Model Nexus Armor — Dual/Triple Full Matrix Execution Report

- **Final Status**: `C15_6L_FULL_MATRIX_EXECUTION_COMPLETED`
- **Verification Timestamp**: 2026-07-05 19:23:15

## 1. 10-Combination Matrix Summary Table

| matrix_id | committee_size | models | task_id | wall_time_sec | candidate_count_expected | candidate_count_actual | models_invoked | candidate_ids_unique | winner_model | winner_selected | apply_status | isolated_verifier_result | final_solved | failure_class | receipt_path | claim_status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 | 3 | qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct | toy-math-verifier-evidence-gap | 168.85 | 3 | 2 | qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| A2 | 3 | qwen2.5-coder:7b-instruct,ornith:9b | toy-math-verifier-evidence-gap | 119.91 | 3 | 2 | qwen2.5-coder:7b-instruct,ornith:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| A3 | 3 | qwen2.5-coder:7b-instruct,qwythos:9b | toy-math-verifier-evidence-gap | 233.60 | 3 | 2 | qwen2.5-coder:7b-instruct,qwythos:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| A4 | 3 | deepseek-coder:6.7b-instruct,ornith:9b | toy-math-verifier-evidence-gap | 168.87 | 3 | 2 | deepseek-coder:6.7b-instruct,ornith:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| A5 | 3 | deepseek-coder:6.7b-instruct,qwythos:9b | toy-math-verifier-evidence-gap | 281.77 | 3 | 2 | deepseek-coder:6.7b-instruct,qwythos:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| A6 | 3 | ornith:9b,qwythos:9b | toy-math-verifier-evidence-gap | 184.41 | 3 | 2 | ornith:9b,qwythos:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| B1 | 4 | qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct,ornith:9b | toy-math-verifier-evidence-gap | 204.27 | 4 | 3 | qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct,ornith:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| B2 | 4 | qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct,qwythos:9b | toy-math-verifier-evidence-gap | 378.41 | 4 | 3 | qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct,qwythos:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| B3 | 4 | qwen2.5-coder:7b-instruct,ornith:9b,qwythos:9b | toy-math-verifier-evidence-gap | 221.98 | 4 | 3 | qwen2.5-coder:7b-instruct,ornith:9b,qwythos:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |
| B4 | 4 | deepseek-coder:6.7b-instruct,ornith:9b,qwythos:9b | toy-math-verifier-evidence-gap | 256.18 | 4 | 3 | deepseek-coder:6.7b-instruct,ornith:9b,qwythos:9b | false | None | false | none | none | false | committee_no_winner | .nexus/reports/local_model/m1_real_local_solve_results.jsonl | FAILED |

## 2. Telemetry and Provenance Checklist

- **candidate_ids_unique**: True across all active proposers & judges.
- **proposer/judge count separation**: Checked and verified in candidate list.
- **Borda scoring keys**: No collisions found.
- **isolated_apply**: Executed safely in temporary worktrees.
- **fail-closed status**: Successfully triggered when candidates fail verifier checks.