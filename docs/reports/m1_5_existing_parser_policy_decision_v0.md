---
status: M1_5_EXISTING_PARSER_POLICY_DECISION_COMPLETE
created: 2026-06-30
scope: decision_report_only
---

# M1.5 Existing Parser Policy Decision Report

## 1. Summary

M1 failed 5/6 tasks on `REPLACEMENT_MARKDOWN_FENCE`. The model wraps valid patches in markdown fences (`\`\`\`python ... \`\`\``), and the `AnchoredEditReplacementGuard` in `SolidSearchReplaceProtocol` rejects this wrapping. This report decides which parser policy M1 should adopt.

---

## 2. Existing Parser Behaviors

### 2.1 SearchReplaceParser (Legacy Parser)

**File**: `nexus/services/local_heal/parser.py`

- `_clean_content()` strips markdown fences via `re.sub(r'```[a-zA-Z0-9]*\n?', '', text).strip()` — removes fence markers, retains content inside.
- Supports multiple formats: Aider-style (`<<<<<<< SEARCH / ======= / >>>>>>> REPLACE`), simple (`SEARCH: ... REPLACE: ... END`), and whole-file replacement.
- Validates: no placeholders (`# ...`, `// ...`), no truncation markers.
- Does NOT reject markdown fences — they are silently stripped.

### 2.2 SolidSearchReplaceProtocol (New Parser, anchored_edit mode)

**File**: `nexus/services/local_heal/protocol.py`

When `protocol_mode == "anchored_edit"` and `anchor_text is not None`:

1. Tries `<<<<<<< REPLACE / >>>>>>> REPLACE` block pattern → extracts replacement.
2. Tries `REPLACE: ... END` simple format → extracts replacement.
3. Tries standard `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE` → extracts REPLACE portion.
4. **Fence check (P9)**: If none of the above match, checks `MARKDOWN_FENCE_PATTERN` against raw output. If matched, **rejects with `REPLACEMENT_MARKDOWN_FENCE`**.
5. Falls back to treating entire output as replacement.
6. Passes replacement through `AnchoredEditReplacementGuard.validate_replacement()`:
   - Rejects empty replacement
   - Rejects markdown fence wrapping (second check — defense-in-depth)
   - Rejects prose contamination (>30% natural language lines)
   - Validates AST syntax

---

## 3. Strict anchored_edit Rationale (Security)

`AnchoredEditReplacementGuard` is intentionally strict because:

1. **Anchored edit replaces a specific code span identified by AST anchor.** The model must output ONLY the replacement code — no wrapping, no prose, no explanation.

2. **Markdown fences could allow injection.** If the parser strips fences and passes content, a malicious or hallucinating model could inject unintended content between the fence markers.

3. **Prose contamination signals hallucination.** When a model outputs "Here is the fix: ..." followed by code, it indicates the model is not following the anchored_edit contract.

4. **Defense-in-depth.** The fence check appears at two levels: line 72 (raw output pre-check) and line 397 (validate_replacement post-check). This ensures fenced output cannot pass even if one check is bypassed.

5. **M1 5/6 failure confirms the guard is working.** The 5 failures are not bugs — they are the guard correctly rejecting non-conforming output. The 1 success shows the model CAN produce correct output when instructed properly.

---

## 4. Security Risk of Stripping Fences

| Risk | Description | Severity |
|------|-------------|----------|
| Injection | Stripping fences could allow model to inject content that isn't valid replacement code | HIGH |
| Duplicate sanitizer | Creating a new fence-stripper when `SearchReplaceParser._clean_content` already exists | MEDIUM |
| Prose passthrough | Fence stripping without prose check could pass "Here is the fix: \`\`\`python ..." | HIGH |
| Verification bypass | If replacement is altered by stripping, verbatim search-match could produce false positives | HIGH |

**Conclusion**: Stripping fences in `anchored_edit` mode is unsafe. The risk of injection outweighs the convenience of accepting fenced output.

---

## 5. Risk of Duplicate Sanitizer

`SearchReplaceParser._clean_content()` already strips markdown fences in legacy format handling. Adding a second fence-stripping mechanism for `anchored_edit` mode would:

- Create inconsistent behavior between legacy and anchored paths
- Increase surface area for bugs (two sanitizers with different edge cases)
- Violate DRY principle without clear benefit

**Conclusion**: Do not create a new sanitizer. Reuse existing June capability.

---

## 6. Existing Retry Mechanism

### 6.1 HealPipeline retry

**File**: `nexus/services/local_heal/pipeline.py`

- `HealContext.max_tries = 3` — the pipeline supports up to 3 attempts.
- `HealOrchestrator` / `CommitteeOrchestrator` runs phases with retry capability.
- `PatchSynthesisPhase` is one of the phases — if it fails (parse failure), the orchestrator can retry.

### 6.2 failure_feedback_builder

**File**: `nexus/services/local_heal/failure_feedback_builder.py`

- `build_failure_feedback()` builds an abbreviated feedback prompt when a patch fails verification.
- Connected in `local_model_executor.py:268-280` — builds feedback from `previous_failure`, `verifier_status`, `stdout_tail`, `stderr_tail`.
- The feedback is appended to the prompt as `failure_context` (line 313-314).
- **Currently, `REPLACEMENT_MARKDOWN_FENCE` is NOT fed back to retry.** The committee path returns empty hash at line 412 and does NOT reach the retry loop.

### 6.3 Committee-to-Repair Seam

**File**: `tests/unit/local_heal/test_committee_to_repair_seam_audit.py`

- When `REPLACEMENT_MARKDOWN_FENCE` is detected in `local_committee_only` topology:
  - `_normalize_candidate_patch` returns `""` (empty patch)
  - Empty hash is committed to candidate
  - Committee path returns at line 412 without reaching `isolated_local_solve_loop` or `diff_repair`
  - `solved=false` — no false positive claimed

---

## 7. Recommendation Ranked

### Rank 1 (Recommended): Option D — Full HealPipeline with Existing Retry

**Approach**: Execute `HealPipeline` (which already has retry policy) and connect `REPLACEMENT_MARKDOWN_FENCE` into the existing `failure_feedback_builder` flow.

**Rationale**:
- The `HealPipeline` already supports `max_tries=3` and orchestrates phases with retry.
- `failure_feedback_builder` already exists and can be enhanced to include fence-stripping instructions.
- No new parser code needed — reuse existing `SolidSearchReplaceProtocol` and `AnchoredEditReplacementGuard`.
- The fence rejection is correct behavior — the fix is to improve the retry prompt, not weaken the parser.

**Implementation sketch**:
1. When `REPLACEMENT_MARKDOWN_FENCE` is detected in committee path, instead of returning empty hash, route the error into `failure_feedback_builder` with an enhanced message: "Your previous patch was wrapped in markdown fences. Output ONLY raw code inside REPLACE block."
2. Feed this enhanced feedback into the next retry attempt.
3. Let `HealPipeline.max_tries=3` handle the retry count.

**Risk**: If the model persistently outputs fences across all retries, the task will exhaust retries and return empty. This is acceptable — it signals the model cannot follow the anchored_edit contract for this task.

### Rank 2 (Alternative): Option C — Strict Parser + failure_feedback Retry

**Approach**: Keep strict `AnchoredEditReplacementGuard` but connect `REPLACEMENT_MARKDOWN_FENCE` error into `failure_feedback_builder` for retry.

**Rationale**:
- Same security posture as Rank 1.
- More targeted: only adds fence-specific feedback, does not require full pipeline execution.
- Risk: If the retry prompt does not explicitly instruct "strip fences", the model may repeat the same output.

**Limitation**: Does not leverage the full pipeline retry loop — only the committee path retry.

### Rank 3 (Not Recommended): Option B — Route Fenced Output to Legacy Parser

**Approach**: When `REPLACEMENT_MARKDOWN_FENCE` is detected, route output to `SearchReplaceParser` which strips fences via `_clean_content`.

**Rationale**:
- Would accept the 5/6 tasks that M1 currently fails.
- Leverages existing legacy parser capability.

**Why not recommended**:
1. **Security risk**: Stripping fences without full `AnchoredEditReplacementGuard` validation could pass prose contamination or injection.
2. **Behavioral inconsistency**: Legacy parser uses different validation (no AST check, no prose check) — routed patches would bypass security gates.
3. **Duplicate sanitizer**: Creates a second fence-handling path when one already exists.
4. **Weakens verification**: The `anchored_edit` path exists precisely because legacy parser was too permissive.

---

## 8. Explicit Constraints

- **Do NOT create a new parser.** Reuse existing `SolidSearchReplaceProtocol` and `AnchoredEditReplacementGuard`.
- **Do NOT strip fences in `anchored_edit` mode.** The rejection is correct behavior.
- **Do NOT weaken `AnchoredEditReplacementGuard` validation.** The guard is working as designed.
- **Do NOT modify `SearchReplaceParser._clean_content`** for `anchored_edit` use cases.
- **Reuse existing June capability**: `failure_feedback_builder`, `HealPipeline` retry, `CommitteeOrchestrator`.

---

## 9. M1 Scope Boundary

This report is decision-only. No code changes, no parser modification, no protocol modification, no sanitizer, no replacement guard change, no benchmark change, no new benchmark run.

**Forbidden claims**:
- Do NOT claim parser fixed.
- Do NOT claim implementation done.
- Do NOT claim solved-rate improved.

---

## 10. Appendix: Key Code Locations

| Component | File | Lines |
|-----------|------|-------|
| `_clean_content` (legacy fence strip) | `nexus/services/local_heal/parser.py` | 9-12 |
| `SolidSearchReplaceProtocol.parse` (anchored_edit branch) | `nexus/services/local_heal/protocol.py` | 41-100 |
| `AnchoredEditReplacementGuard` (fence + prose rejection) | `nexus/services/local_heal/protocol.py` | 355-439 |
| `MARKDOWN_FENCE_PATTERN` | `nexus/services/local_heal/protocol.py` | 374-376 |
| `build_failure_feedback` | `nexus/services/local_heal/failure_feedback_builder.py` | 5-42 |
| `failure_feedback` integration in executor | `nexus/services/local_heal/local_model_executor.py` | 256-282 |
| `HealPipeline.max_tries` | `nexus/services/local_heal/pipeline.py` | 45 |
| Committee parse failure → empty hash | `nexus/services/local_heal/local_model_executor.py` | 695-700 |
| Test: REPLACEMENT_MARKDOWN_FENCE rejection | `tests/unit/local_heal/test_anchored_edit.py` | 130-136, 280-293 |
| Test: committee seam audit | `tests/unit/local_heal/test_committee_to_repair_seam_audit.py` | 109-144 |
