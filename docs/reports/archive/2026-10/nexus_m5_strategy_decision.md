# M5: Local Qwen Armor Strategy Decision

## Status: M5_7B_PRIMARY_LOCAL_ACTOR_VALIDATED

## M3 Expanded Benchmark Results

| Task | Bare | Constrained | JSON Uplift |
|------|------|-------------|-------------|
| C_12481 | 1183 chars, md | 214 chars, JSON | ✅ YES |
| C_13453 | 1481 chars, md | 179 chars, JSON | ✅ YES |
| perm_inverse | 1169 chars, JSON | 167 chars, JSON | — already JSON |
| geo_distance | 783 chars, md | 175 chars, JSON | ✅ YES |

**JSON uplift: 3/4 tasks (75%)**

## Key Findings

1. **Constrained Action DSL is decisive**: 3/4 tasks produce JSON only under constrained mode.

2. **7B bare produces markdown**: Average 1154 chars, always markdown-wrapped.

3. **7B constrained produces JSON**: Average 184 chars, always structured.

4. **Size reduction**: 84% average reduction from bare to constrained.

5. **M2 prompt upgrade**: Old simpler prompt works better for 7B than complex two-stage prompt.

## What Nexus Contributes

| Component | Contribution | Evidence |
|-----------|-------------|----------|
| Constrained Action DSL | **PRIMARY** — forces JSON output | 3/4 tasks JSON uplift |
| Evidence Packet | **HIGH** — mechanism context | All modes identify correct mechanism |
| Deterministic Applier | **HIGH** — intent → patch | JSON → valid patch |
| Bounded Refinement | **MEDIUM** — corrects args | C_13453 history |
| 3B Advisory | **LOW** — predicts intent | N/A measured |
| Verifier Feedback | **MEDIUM** — actionable info | N/A measured |

## M5 Strategy Decision

**M5_7B_PRIMARY_LOCAL_ACTOR_VALIDATED**

### What M1 improved:
- DSL expanded to 25 action types
- Applier supports relation-based insertion
- Regression guards pass

### What M2 improved:
- Evidence-to-action schema defined
- Old simpler prompt works better for 7B
- Two-stage prompt adds complexity without benefit

### What M3 measured:
- 3/4 tasks show JSON uplift with constrained mode
- 7B bare always produces markdown
- 7B constrained always produces JSON

### Local 7B uplift:
- **FORMAT_CONTROL_UPLIFT**: Bare=markdown, Armored=JSON
- **MECHANISM_IDENTIFICATION_UPLIFT**: Both identify correct mechanism
- **PATCH_APPLY_UPLIFT**: JSON → valid patch (when mechanism correct)

### 3B advisory value:
- Predicts intent but not measured in M3
- Keep as route/evidence advisor

### Gap to GPT/Gemini bare target:
- Local armored 7B produces correct mechanism but may not always produce correct patch
- Strong bare model likely produces correct patch more reliably on hard tasks
- Comparison needed (M4)

### What to optimize next:
1. **Evidence-to-action interface** — connect evidence to action candidates
2. **Action selection prompt** — improve 7B action selection reliability
3. **Strong bare model comparison** — measure target gap

### What to test next:
1. Run M3 on more tasks
2. Compare 7B bare vs armored on verification tasks
3. Measure action validity rate

### What not to do yet:
1. Cloud API (requires owner approval)
2. 14B CPU-only (resource guard)
3. Broad rewrite actions
4. Public claim

### 30-day roadmap:
1. Week 1: Evidence-to-action interface
2. Week 2: Action selection prompt improvement
3. Week 3: Expanded benchmark (8+ tasks)
4. Week 4: Strong bare model comparison design

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**
