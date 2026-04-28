---
name: nexus-benchmark-continuous-optimization
description: Use when optimizing Nexus and needing a repeatable before/after benchmark loop that compares the same model bare vs the same model wearing Nexus, tracks verified delivery, cost, friction, public claim gate, and rule lifecycle decisions.
---

# Nexus Benchmark Continuous Optimization

## What

Run a fixed, repeatable optimization loop for Nexus:

1. Freeze the task set, model, timeout, hidden verifier, and eligibility rules.
2. Run the same model bare.
3. Run the same model wearing Nexus.
4. Compare verified delivery, trust mismatch, wall time, tokens, model calls, Nexus wearing, and public gate.
5. Emit rule lifecycle recommendations.
6. Decide whether the change should be kept, reverted, light-routed, or promoted.

## Why

Nexus is a battlesuit, not a separate solving agent. Its value must be measured as the lift it gives the same model through context, routing, governance, memory, self-heal, and evidence verification.

As base models improve, some Nexus rules may become unnecessary. This loop keeps Nexus from becoming heavy static ceremony: rules that no longer add value can move toward light mode or deprecation; rules that still improve verified delivery stay active.

## How

### Preflight

- Confirm model quota.
- Confirm no benchmark/Gemini process is already running.
- Record current git commit and dirty status.
- Use hidden verifier for value claims.
- Keep infra failures out of solve-rate denominators.

### Standard Public Candidate

Use the current public RLM harder benchmark when proving governance/evidence/RLM value:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=240 \
NEXUS_RLM_REPAIR_LOOP=1 \
NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=180 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_rlm_harder_v2.json \
  --output-dir .nexus/reports/bench_gemini3flash_rlm_v2_<tag> \
  --max-tasks 8 --repeat-trials 2 --timeout-sec 300 \
  --total-timeout-sec 7200 --stop-loss-sec 7200 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter all --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

### Required Report Fields

- Same model in both arms.
- `run_eligible` and `infra_invalid_reason`.
- Solve rate and eligible solve rate.
- Semantic verified rate.
- Trust mismatch.
- Avg/P50/P95 wall time when available.
- Tokens and model calls per verified success.
- Nexus wearing validity.
- Five pillars and six phases.
- MSA flags with evidence-backed Swarm/Drone/Nightshift fields.
- RLM trace present rate when RLM is enabled.
- Rule lifecycle recommendations: `active`, `light`, `deprecated`, `removed_candidate`.
- Public claim gate verdict.

### Before / After Optimization

When measuring a Nexus change, run the same benchmark twice:

1. Before change: current committed Nexus.
2. After change: candidate Nexus.
3. Same model, same task manifest, same trials, same timeout policy.
4. Compare `rule_lifecycle`, verified delivery, trust mismatch, wall time, and cost per verified success.

Do not claim an optimization improved Nexus if the task set, model, eligibility, or verifier changed between runs.

### RLM On / Off

When validating RLM specifically, compare:

1. Bare model.
2. Model wearing Nexus with RLM off.
3. Model wearing Nexus with `NEXUS_RLM_REPAIR_LOOP=1`.

RLM value should be reported as:

- `rlm_trace_present_rate`
- second-round repair wins
- budget exhaustion rate
- time to verified
- trust mismatch change
- cost delta

### Decision Rules

- `Public claim gate: FAIL`: no public claim; diagnose and rerun.
- Nexus wins verified delivery but costs too much: keep full Nexus for high risk and route low risk to light Nexus.
- Bare catches up for a rule across repeated runs: mark the rule as `light_candidate`.
- Nexus still wins on governance/evidence/trust: keep rule `active`.
- Trust mismatch increases: revert or block promotion.

### Output Shape

Use Chinese What / Why / How in final reports:

- What changed.
- Why it matters.
- How it was verified.
- What improved and by how much.
- What still costs too much.
- What the next optimization should target.
