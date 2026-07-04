# C15-6A: Model Output Understanding Layer Reframe

**Date**: 2026-07-04  
**Status**: `PLANNING_REALIGNMENT_ONLY`

## 1. Task

```text
Realign the local-model integration line away from
"make the model obey Nexus patch protocol"
and toward
"make Nexus understand, normalize, verify, and safely apply usable model output".
```

## 2. Current Truth

```text
What C15-5E through C15-5H proved:
- The existing pipeline had real bridge defects.
- Valid model output could be dropped before isolated apply.
- Unified diff acceptance is a real compatibility need for small local models.

What C15-5E through C15-5H did NOT prove:
- that unified diff should become the main product abstraction
- that local models are now using full Nexus capability
- that the committee path is generally solved
- that benchmark success equals runtime capability closure
```

## 3. Product Direction

```text
Model = proposer
Nexus = understanding layer + normalization layer + safety layer
```

Target runtime shape:

```text
Raw model output
-> Output Understanding
-> CanonicalPatchCandidate
-> Source anchoring
-> Isolated apply
-> Verifier
-> Receipt
-> Committee / winner selection
```

Non-target shape:

```text
Raw model output
-> unified diff special case
-> SSRP conversion
-> apply
```

## 4. Why This Reframe Is Needed

### 4.1 Evidence from current line

```text
- C15-5E added deterministic unified-diff-to-SSRP bridging because small local
  models often emit unified diff.
- C15-5H found real receiver bugs, not model-quality bugs:
  - localized_files type mismatch
  - repair_spec telemetry attachment drift
- 2026-07-04 lesson entries show committee runtime can still bypass converted
  candidates or silently fail on fixture/path mismatch.
```

### 4.2 Risk if we keep the current focus

```text
If the next phase keeps asking only
"can live models emit valid unified diff?"
the architecture drifts into format-specific protocol work.

That narrows Nexus into a format adapter instead of a model-output interpreter.
```

## 5. C15-6A Scope

### 5.1 Canonical output contract

Define a single internal object:

```text
CanonicalPatchCandidate
```

Minimum fields:

```text
- candidate_id
- source_format
- target_file
- target_symbol
- old_block
- new_block
- line_span
- anchors
- extraction_confidence
- normalization_steps
- safety_flags
- raw_output_hash
- model_name
```

### 5.2 Output classes Nexus must understand

```text
1. SEARCH_REPLACE
2. UNIFIED_DIFF
3. PARTIAL_DIFF
4. LINE_SPAN_EDIT
5. FUNCTION_REPLACEMENT
6. NATURAL_LANGUAGE_REPAIR_INTENT
7. EMPTY_OR_REFUSAL
8. MALFORMED_OUTPUT
```

### 5.3 Fallback order

```text
SEARCH_REPLACE
-> UNIFIED_DIFF
-> PARTIAL_DIFF
-> LINE_SPAN_EDIT
-> FUNCTION_REPLACEMENT
-> NATURAL_LANGUAGE_REPAIR_INTENT
-> reject / escalate
```

## 6. Runtime Boundaries

### 6.1 Keep

```text
- CapabilityPlanner remains route authority
- verifier remains truth authority
- candidate isolation remains fail-closed
- committee remains downstream selection/execution logic
```

### 6.2 Do not do

```text
- do not move route authority into committee
- do not claim local-model armor ready
- do not widen apply semantics with fuzzy matching
- do not hardcode benchmark-only transformations into production success claims
- do not treat unified diff as the canonical public contract
```

## 7. Execution Plan

### Phase A: Contract

```text
Goal:
Introduce CanonicalPatchCandidate and OutputUnderstandingResult contracts
without changing route authority.

Acceptance:
- pure tests for output classification and candidate normalization
- one receipt field records source_format and normalization_steps
```

### Phase B: Interpreter

```text
Goal:
Add an interpreter that classifies raw model output and extracts the strongest
usable candidate.

Acceptance:
- SSRP, unified diff, line-span, and function replacement all normalize into
  the same candidate contract
- malformed and refusal outputs fail closed with explicit reason
```

### Phase C: Anchoring

```text
Goal:
Bind normalized candidates back to real source with exact file/symbol/span/hash
guards before isolated apply.

Acceptance:
- target binding is explicit in receipts
- ambiguous anchors reject before apply
```

### Phase D: Committee integration

```text
Goal:
Committee compares normalized candidates, not raw format strings.

Acceptance:
- committee receipts show per-candidate source_format
- converted candidates cannot bypass apply/verify
- zero-winner committee exits fail-closed without redundant retry
```

### Phase E: Evidence

```text
Goal:
Separate bounded benchmark proof from "full Nexus capability" claims.

Acceptance:
- benchmark lane proves interpreter/normalizer behavior
- live runtime lane proves committee + isolation + verifier wiring
- no claim crosses from lane A into lane B without direct evidence
```

## 8. Local Model Committee Position

```text
The local model committee is still useful, but only after outputs are normalized.

Committee should compare canonical candidates.
Committee should not become a patch-format workaround layer.
Committee should not own planner or verifier authority.
```

## 9. Immediate Next Step

```text
Replace "C15-5I: Live Committee Bridge Validation" as the main line with:

C15-6A: Canonical Model Output Understanding Layer
```

Immediate deliverables:

```text
1. contract draft for CanonicalPatchCandidate
2. output class taxonomy
3. interpreter fallback order
4. receipt additions for source_format / normalization_steps / anchor_status
5. narrow migration plan from unified-diff bridge into generalized understanding
```

## 10. Residual Debt

```text
- delegated retry solved remains unproven
- committee live winner proof remains limited
- benchmark evidence still does not prove full Nexus capability closure
- current runtime still carries format-specific recovery logic that needs
  consolidation under a generalized interpreter
```
