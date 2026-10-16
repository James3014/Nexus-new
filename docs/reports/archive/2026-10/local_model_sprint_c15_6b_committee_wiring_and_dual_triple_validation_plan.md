# C15-6B: Committee Wiring and Dual/Triple Model Validation Plan

**Date**: 2026-07-04  
**Status**: `EXECUTION_PLAN_READY`

## 1. Task

```text
Complete the runtime wiring required for local-model committees to use Nexus
capabilities as proposers, then validate both 2-model and 3-model committees
on the same Nexus understanding/apply/verifier path.
```

## 2. Current Truth

### Proven already

```text
- Committee proposer/judge contract exists and has focused tests.
- delegated_retry_committee_path_used=true has been observed in live runs.
- isolated apply and verifier can be reached for some committee candidates.
- unified diff acceptance is a real compatibility need for local models.
```

### Not proven yet

```text
- that committee candidates always pass through a generalized output
  understanding layer before apply
- that 2 distinct proposer models really execute and produce distinct runtime
  candidates in the same solve attempt
- that 3 distinct proposer models really execute and produce distinct runtime
  candidates in the same solve attempt
- that a committee winner can be selected, applied, and verified with full
  selected/applied/hash truth
- that committee solve capability is connected to Nexus end-to-end on a real
  task beyond benchmark-only wiring evidence
```

## 3. Primary Blockers

### Blocker A: runtime model wiring

```text
Earlier reports showed the benchmark path hardcoding executor/signal_snapshot
fields, preventing true heterogeneous committee trials from being exercised
through the normal runtime path.
```

### Blocker B: output understanding gap

```text
Committee paths can still over-focus on raw patch format handling instead of
normalizing all usable model outputs into one internal candidate contract.
```

### Blocker C: committee truth chain

```text
Even when committee path is entered, we still need current-proof that:
- per-candidate model execution is real
- normalization occurred
- isolated apply occurred
- verifier occurred
- winner selection matches applied candidate
```

## 4. Product Target

```text
Model = proposer
Nexus = output understanding + normalization + source anchoring +
        isolated apply + verifier + receipt + winner selection
```

Target path:

```text
Raw committee proposer output
-> OutputUnderstandingResult
-> CanonicalPatchCandidate
-> Source anchoring
-> Isolated apply
-> Verifier
-> Committee selection
-> Final receipt truth
```

## 5. Phase Plan

### Phase 1: Wiring Closure

Goal:

```text
Remove the runtime bottlenecks that prevent true dual-model and triple-model
committee execution from being exercised through the same Nexus path.
```

Required work:

```text
1. Ensure runtime model selection is not silently collapsed to one executor
   model when committee proposer_specs are provided.
2. Ensure committee candidate generation records the real proposer model used
   at the model-call boundary.
3. Ensure committee path emits receipt truth for:
   - proposer model
   - raw output class
   - source_format
   - normalization result
   - isolated apply attempted
   - verifier attempted
```

Acceptance gate:

```text
G1-A
Given 2 proposer models, runtime receipt shows candidate_count=2 and 2 distinct
proposer model names at call-boundary truth, not just labels.

G1-B
Given 3 proposer models, runtime receipt shows candidate_count=3 and 3 distinct
proposer model names at call-boundary truth, not just labels.

G1-C
No route authority change. Planner remains upstream authority.
```

### Phase 2: Output Understanding Integration

Goal:

```text
Make committee candidates pass through generalized output understanding before
apply, instead of format-specific branches being treated as the core behavior.
```

Required work:

```text
1. Introduce CanonicalPatchCandidate and OutputUnderstandingResult contracts.
2. Normalize at least:
   - SEARCH_REPLACE
   - UNIFIED_DIFF
   - LINE_SPAN_EDIT
   - FUNCTION_REPLACEMENT
   - EMPTY / REFUSAL / MALFORMED
3. Add receipt truth:
   - source_format
   - normalization_steps
   - anchor_status
```

Acceptance gate:

```text
G2-A
Committee apply path consumes canonical candidates, not raw-format-specific
special cases.

G2-B
Converted unified diff candidates cannot bypass isolated apply/verify.

G2-C
Malformed or ambiguous candidates fail closed before apply with explicit reason.
```

### Phase 3: Dual-Model Validation

Goal:

```text
Prove that a 2-model committee can run through Nexus understanding, isolation,
verifier, and winner selection.
```

Validation sets:

```text
Set D1: ornith:9b + qwythos:9b
Set D2: qwen2.5-coder:7b-instruct + ornith:9b
Set D3: deepseek-coder:6.7b-instruct + ornith:9b
```

For each set, validate two lanes:

```text
Lane A: wiring/understanding lane
- both proposers executed
- both candidates normalized or explicitly rejected
- apply/verifier receipts truth-complete

Lane B: solve lane
- winner selected or no-winner reason explicit
- if winner exists, selected_candidate_hash_matches_applied=true
- verifier_result=pass required for solved=true
```

Acceptance gate:

```text
G3-A
candidate_count=2 with distinct proposer execution evidence

G3-B
Each candidate has one complete truth record:
- source_format
- normalization outcome
- apply outcome
- verifier outcome

G3-C
If no winner, solved=false and no_winner_reason must be explicit.

G3-D
If winner exists, selected/applied/hash/verifier truth must all align.
```

### Phase 4: Triple-Model Validation

Goal:

```text
Prove that a 3-model committee can run through the same Nexus path with true
multi-proposer execution and truthful winner/no-winner outcomes.
```

Validation sets:

```text
Set T1: qwen2.5-coder:7b-instruct + deepseek-coder:6.7b-instruct + ornith:9b
Set T2: deepseek-coder:6.7b-instruct + ornith:9b + qwythos:9b
```

Acceptance gate:

```text
G4-A
candidate_count=3 with 3 distinct proposer execution records

G4-B
All 3 candidates reach understanding receipt projection

G4-C
Committee judge/winner truth appears in receipt without overriding verifier

G4-D
If solved=true, selected candidate is the applied candidate and verifier_result=pass
```

### Phase 5: Solve Claim Gate

Goal:

```text
Separate "wiring works" from "committee can solve using Nexus capabilities".
```

Required evidence tiers:

```text
Tier 1: controlled toy task
Tier 2: verifier-evidence-gap task
Tier 3: one real small repo task
```

Claim policy:

```text
Only Tier 1 pass:
  wiring proven, solve capability not yet proven broadly

Tier 1 + Tier 2 pass:
  committee path uses Nexus capability chain on nontrivial verifier feedback

Tier 1 + Tier 2 + Tier 3 pass:
  bounded committee solve claim allowed for this lane
```

## 6. Suggested Execution Order

```text
1. Phase 1 wiring closure
2. Phase 2 output understanding integration
3. Dual-model validation: D1 -> D2 -> D3
4. Triple-model validation: T1 -> T2
5. Solve claim gate
```

Reason:

```text
Do not start 3-model validation before 2-model wiring truth is stable.
Do not claim solve capability from committee path before canonical candidate
understanding is in place.
```

## 7. Worker Packets

### Packet A: cheap read-only checker

Scope:

```text
Audit current committee runtime path for:
- executor model collapse
- proposer_specs preservation
- receipt truth fields already present / missing
```

Allowed outputs:

```text
- file/line references
- missing truth-field checklist
- no code changes
```

### Packet B: bounded contract implementer

Scope:

```text
Implement CanonicalPatchCandidate + OutputUnderstandingResult contracts and
pure normalization tests only.
```

Forbidden:

```text
- no planner changes
- no verifier changes
- no benchmark-only monkeypatches
```

### Packet C: committee telemetry implementer

Scope:

```text
Add per-candidate receipt truth for source_format, normalization, apply, and
verifier status.
```

Forbidden:

```text
- no new route
- no relaxed apply semantics
```

### Packet D: validation runner

Scope:

```text
Run dual-model / triple-model validation matrix after Phases 1-2 are merged.
Produce truth tables only.
```

Forbidden:

```text
- no claim inflation
- no "solved" claim unless verifier_result=pass and selected/applied/hash align
```

## 8. Commit Strategy

```text
Commit 1:
Phase 1 wiring closure

Commit 2:
Phase 2 canonical candidate + understanding layer

Commit 3:
Dual-model validation evidence

Commit 4:
Triple-model validation evidence

Commit 5:
Solve claim gate report
```

## 9. Forbidden Shortcuts

```text
- do not fake multi-model by changing only labels
- do not treat benchmark-only mock output as committee solve proof
- do not let judge output override verifier
- do not widen parser/apply semantics just to increase pass rate
- do not claim "full Nexus capability" from toy-only evidence
- do not move route authority into committee
```

## 10. Exit Criteria

```text
The lane is considered connected only when:
1. 2-model committee proves distinct proposer execution truth
2. 3-model committee proves distinct proposer execution truth
3. committee candidates pass through Nexus understanding -> apply -> verifier
4. selected candidate truth matches applied candidate truth
5. at least one bounded solve claim passes the solve gate without violating
   fail-closed rules
```

## 11. Residual Risk

```text
- some model combinations may remain too slow or too weak even after wiring fix
- output understanding may normalize more candidates but still expose model
  quality ceiling
- real-task pass rate may still lag even when committee wiring is complete
```

Interpretation:

```text
If that happens, the next blocker is model quality or cost/runtime budget,
not Nexus committee wiring.
```
