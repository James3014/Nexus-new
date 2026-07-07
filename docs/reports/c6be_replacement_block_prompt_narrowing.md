# C6BE: Multi-line Locked Search Prompt Narrowing

## Objective
Fix `REPLACEMENT_PROSE_CONTAMINATION` bottleneck from C6BD — when `locked_search` is a multi-line (6-line) block, the 7B model degenerates from code-only REPLACE output to prose contamination. Fix via prompt narrowing (visual anti-prose examples), not parser/committee/verifier changes.

## Changes

### 1. Prompt narrowing (both sites)
**Files**: `local_committee_candidate_provider.py:116-132`, `local_model_executor.py:2480-2498`

Before:
```
Output format (required — exactly this, nothing else):
<<<<<<< REPLACE
[replacement code goes here]
>>>>>>> REPLACE

WRONG — do NOT do this (will be REJECTED):
```
<<<<<<< REPLACE
[code]
>>>>>>> REPLACE
```

Output ONLY the REPLACE block. No backticks. No extra text.
```

After:
```
Output format (required — exactly this, nothing else):
<<<<<<< REPLACE
...
>>>>>>> REPLACE

WRONG — backtick-wrapped (will be REJECTED):
```
<<<<<<< REPLACE
...
>>>>>>> REPLACE
```

WRONG — explanations before or after the REPLACE block (will be REJECTED):
# Here is the fix
<<<<<<< REPLACE
...
>>>>>>> REPLACE

Output ONLY code between <<<<<<< and >>>>>>>. No backticks. No explanations. No comments. Code only.
```

Key changes:
- Added second WRONG example showing prose contamination (`# Here is the fix`)
- Changed `[replacement code goes here]` → `...` (prose placeholder → code-like)
- Changed `[code]` → `...` for consistency
- Reinforced "No explanations. No comments. Code only."

### 2. Prose threshold false positive fix
**File**: `protocol.py:458-459`

Before:
```python
code_lines = sum(1 for l in non_empty_lines if prose_markers.match(l))
```

After:
```python
code_lines = sum(1 for l in non_empty_lines if prose_markers.match(l))
code_lines += sum(1 for l in non_empty_lines if l.strip().startswith('#'))
```

The prose threshold check (step 4) undercounted code-like lines when the replacement contained Python comments — comment lines (`# ...`) were not counted as code-like. Added explicit comment-line counting to prevent false positives on legitimate multi-line code replacements.

### 3. Tests
- `test_c6be_multiline_anchor_contract.py`: 6 new tests
  - Contract: both prompt sites include anti-prose WRONG example
  - RED: multi-line locked_search + prose inside REPLACE → `REPLACEMENT_PROSE_CONTAMINATION`
  - GREEN: multi-line locked_search + code-only REPLACE → valid unified diff
  - Regression: fence-unwrap, identical-replacement guards for multi-line case
- `test_c6bg_replace_syntax_contract.py`: Updated assertions for new WRONG wording

## Results

### Live Rerun (astropy__astropy-13236, local_committee_only)

| Metric | C6BD (before) | C6BE (after) |
|--------|---------------|--------------|
| `protocol_parse_failed` | `True` | **`False`** ✓ |
| `error_kind` | `REPLACEMENT_PROSE_CONTAMINATION` | **`none`** ✓ |
| `selected_candidate_hash` | `e3b0c442...` (empty) | **`cca1fe5b...`** (non-empty) ✓ |
| `isolated_apply_status` | never reached | **`applied`** ✓ |
| `isolated_verifier_status` | never reached | `fail` |

C6BE successfully resolved the prose contamination bottleneck. The pipeline now reaches apply + verifier. The new bottleneck is semantic correctness — the model's replacement was syntactically valid and applied but did not remove `view(NdarrayMixin)`.

### Committee breakdown
- **qwen2.5-coder:7b-instruct** (primary): Hash `88998d10...`, selected, applied, verifier=fail
- **deepseek-coder:6.7b-instruct** (secondary): Hash `64626b77...`, not selected
- **qwen2.5-s2t-advisor:3b** (judge): Not applicable (no patch)

### Test results
- 16/16 C6 tests pass (6 new C6BE + 6 C6BG + 4 C6BD)
- Full local_heal unit suite: 1124 pass, 64 pre-existing failures (pipeline integration tests)

## Residual Debt

1. **Semantic correctness**: Pipeline now reaches apply + verifier, but verifier fails. Next bottleneck is model output correctness, not format/contract. C6BF area.
2. **Prompt drift risk**: Two copies of the prompt contract (committee + executor). If C6BE prompt changes prove insufficient, recommend unifying into shared template.
3. **Prose-detection limitation**: Preamble prose (text before REPLACE markers) is silently ignored, not rejected. If model output prose before markers, it passes through unseen.

## Files Touched
| File | Change |
|------|--------|
| `nexus/services/local_heal/local_committee_candidate_provider.py` | Prompt narrowing (anti-prose WRONG example) |
| `nexus/services/local_heal/local_model_executor.py` | Prompt narrowing (anti-prose WRONG example) |
| `nexus/services/local_heal/protocol.py` | Prose threshold: count `#` comment lines as code-like |
| `tests/unit/local_heal/test_c6be_multiline_anchor_contract.py` | 6 new tests |
| `tests/unit/local_heal/test_c6bg_replace_syntax_contract.py` | Updated assertions for new WRONG wording |
