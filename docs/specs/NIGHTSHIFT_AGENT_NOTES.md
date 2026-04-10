# NightShift Agent Notes (Quota/Convergence Guard)

## Mandatory preflight before running NightShift
1. Confirm target is a real file path (e.g. `nexus/.../*.py`) and not only a logical task id.
2. Confirm Gemini CLI is available (`gemini --help`).
3. Confirm OAuth session is valid (`gemini` can return a normal response).
4. Set bounded gateway runtime to avoid long stalls:
   - `export NEXUS_GATEWAY_TIMEOUT_SEC=45`
   - `export NEXUS_GATEWAY_MAX_RETRIES=1`

## Model switching policy (required)
- Use both models with automatic failover:
  - primary: `gemini-3.1-pro-preview`
  - fallback: `gemini-3-flash-preview`
- If one model returns quota/capacity failure (`429`, `QUOTA_EXHAUSTED`, timeout-capacity signature), immediately switch to the other.
- If both models are exhausted, NightShift must stop early (`MODEL_EXHAUSTED`) and not keep looping dry retries.

## Run policy
- For smoke run: `--max_rounds 1 --convergence_patience 1`.
- For real run: keep convergence patience <= 5.
- Stop immediately on quota/capacity generation failures to avoid token/time waste.

## Post-run checks
1. Verify `tracelog_*.jsonl` has explicit status (e.g. `SCORED`, `MODEL_EXHAUSTED`, `GENERATION_FAILED`).
2. If `MODEL_EXHAUSTED` or repeated `GENERATION_FAILED` appears, do not continue; wait for quota reset or change model/provider.
3. Only proceed to `--approve` when score > 0 and patch exists.

## Anti-regression reminders
- Never run multiple full `pytest` sessions in parallel (can cause false "system abnormal" symptoms).
- Kill stale `pytest`/NightShift processes before a new verification round.
- Record each failure pattern into Learning Closure Matrix.
