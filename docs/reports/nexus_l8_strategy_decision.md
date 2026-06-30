# L8: Strategy Decision — How to Reach Local Qwen Armor Goal

## Status: L8_OPTIMIZE_ACTION_DSL_NEXT

## L7 Uplift Benchmark Results

| Mode | Chars | Markdown | JSON | Cycle | Uplift |
|------|-------|----------|------|-------|--------|
| 7B Bare | 1550 | ✅ | ❌ | ✅ | — baseline |
| 7B Evidence-Only | 316 | ✅ | ❌ | ✅ | 79% size reduction |
| 7B Constrained | 203 | ❌ | ✅ | ✅ | 87% size reduction, structured |
| 7B Full Armor | 290 | ❌ | ✅ | ✅ | 81% size reduction, structured |

## Key Findings

1. **Constrained Action DSL is decisive**: Bare model produces 1550-char markdown explanation; armored produces 203-char JSON with correct mechanism.

2. **Evidence helps but DSL is primary**: Evidence-only reduces size but still produces markdown. Constrained action forces structured output.

3. **7B identifies correct mechanism under armor**: All modes mention `Cycle(*args)`, but only constrained/armored produce parseable output.

4. **Full armor adds refinement hints**: Armor mode includes confidence and expected_effect, slightly larger but more structured.

## What Nexus Contributes

| Component | Contribution | Evidence |
|-----------|-------------|----------|
| Constrained Action DSL | **PRIMARY** — forces structured JSON | Bare=markdown, Armored=JSON |
| Evidence Packet | **HIGH** — correct mechanism context | All modes mention Cycle |
| Deterministic Applier | **HIGH** — converts intent to valid patch | JSON → patch |
| Bounded Refinement | **MEDIUM** — corrects wrong args | C_13453 refinement history |
| 3B Advisory | **LOW** — predicts intent | N/A for this task |
| Verifier Feedback | **MEDIUM** — actionable failure info | N/A for this task |

## L8 Strategy Decision

**L8_OPTIMIZE_ACTION_DSL_NEXT**

### What to optimize next:
1. **Action DSL expansion** — add more safe action types (REPLACE_RAISE_WITH_EXPR, etc.)
2. **Evidence-to-action interface** — transform evidence into action-relevant fields
3. **Action selection prompt** — improve 7B action selection reliability

### What to test next:
1. Run L7 benchmark on more tasks (easy_localized, medium_semantic)
2. Compare 7B bare vs armored on verification tasks
3. Measure action validity rate across task types

### What not to do yet:
1. Cloud API comparison (requires owner approval)
2. 14B CPU-only (resource guard)
3. Broad rewrite actions (safety boundary)
4. Public claim (internal-only)

### 30-day execution plan:
1. Week 1: L6 DSL expansion + applier fixtures
2. Week 2: L7 expanded benchmark (8+ tasks)
3. Week 3: Evidence-to-action interface
4. Week 4: Strategy refinement based on results

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**
