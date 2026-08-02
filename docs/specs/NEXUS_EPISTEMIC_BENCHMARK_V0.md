# Nexus Epistemic Workflow Benchmark v0

**Schema**: `nexus.epistemic_benchmark_report.v0`  
**Status**: Candidate — awaiting independent acceptance (ERB-01-INDEPENDENT-ACCEPTANCE)  
**Implementation commit**: feat(research): add epistemic benchmark evaluation and reports

---

## 1. Benchmark Problem

How much does the *structure of the review process* affect a reviewer's ability to correctly detect defects, appropriately abstain, and avoid false acceptances — when *all reviewers receive identical source content*?

This benchmark compares **three review protocol arms** applied to the same synthetic corpus of acceptance decisions. It measures reviewer accuracy under:

- **Arm A**: Basic independent review (minimal instruction)
- **Arm B**: Structured review with a versioned strong-protocol checklist
- **Arm C**: Epistemic Workflow review (same checklist + structural isolation, object bindings, and verification metadata)

> This benchmark does **not** claim Arm C will outperform Arm B. All deltas are descriptive.

---

## 2. Three Arms

### Arm A — Standard Review

- Receives: task contract, candidate summary, materials, available evidence refs, response contract
- Review instruction: *"Independently review the candidate and return ACCEPT, REJECT, or BLOCK."*
- No deliberate weakening: no misleading instructions, no trust-the-implementer pressure

### Arm B — Strong Protocol

- Receives: identical materials as Arm A
- Additional: `STRONG_PROTOCOL_V1` versioned checklist (14 items)
- Checklist covers: task contract verification, mandatory check execution, test deduplication, skipped scope, verifier read-only, artifact binding, cross-run references, valid-hash semantic mismatch, authority unlock, negative controls, evidence sufficiency, narrative vs evidence distinction, maximum supportable claim

### Arm C — Epistemic Workflow

- Receives: identical materials as Arm B, including the **same** `STRONG_PROTOCOL_V1` checklist
- Additional structure:
  - `object_bindings`
  - `source_lineage`
  - `extraction_assessment_separation`
  - `verification_status`
  - `cannot_establish_flags`
  - `conflicts`
  - `authority_locks`
  - `review_report`
- **No additional source facts**: Arm C receives the same factual content as Arm B

---

## 3. Fairness Invariants

| Invariant | Enforcement |
|-----------|-------------|
| Same task contract across arms | `common_materials_sha256` must be identical |
| Same candidate summary across arms | Included in `common_materials_sha256` |
| Same materials across arms | Included in `common_materials_sha256` |
| Same response contract across arms | Verified per packet |
| Arm B checklist not weakened | Checklist has 14 mandatory items |
| Arm C uses same checklist as Arm B | Overlay includes full `STRONG_PROTOCOL_V1` |
| No extra source facts in Arm C | Only structural metadata added |
| Oracle not present in packets | Leakage scanner enforced at generation |
| Real `case_id` not in packets | Deterministic opaque aliasing |

---

## 4. Corpus Categories

**Corpus version**: `v0`  
**Total cases**: 18

| Category | Case IDs | Oracle |
|----------|----------|--------|
| CLEAN (ACCEPT expected) | EBR-001, EBR-018 | 2 cases |
| DEFECTIVE (REJECT expected) | EBR-002 through EBR-015 | 14 cases |
| INDETERMINATE (BLOCK expected) | EBR-016, EBR-017 | 2 cases |

Defect categories covered:
- Duplicate test collection
- Mandatory check not executed
- Verifier mutates state
- Valid hash with semantic mismatch
- Cross-run / cross-claim binding errors
- Derivative evidence inflation
- Cannot-establish gap
- Stale decision trace
- Hidden skipped scope
- Source prompt injection / authority breach
- Report tamper with recomputed hash
- Unauthorized public claim unlock
- Source updated after receipt

Each case has:
- ≥ 2 public materials (with recomputable SHA-256)
- ≥ 1 available evidence reference
- Neutral title (does not reveal defect type)
- Observable defect from public materials only

---

## 5. Oracle Isolation

The oracle (`oracle_v0.json`) is **never written to the run directory** or any public output.

Oracle fields that must not appear in public packets or output:
- `oracle_class`
- `oracle_decision`
- `known_defects`
- `defect_id`
- `required_detection`
- `oracle_sha256`
- Real `case_id` (opaque aliases used instead)

**Alias derivation**: `HMAC-SHA256(key=(seed‖arm), msg=case_id)`, truncated to 12 hex chars. Different arms for the same case receive different aliases.

---

## 6. Packet Contract

Each packet schema (`nexus.epistemic_benchmark_packet.v0`) contains:

```yaml
schema: nexus.epistemic_benchmark_packet.v0
benchmark_run_id:         # Run identifier
arm:                       # standard_review | strong_protocol | epistemic_workflow
arm_protocol_version:      # e.g. "STRONG_PROTOCOL_V1"
case_alias:                # Opaque, arm-specific, deterministic alias
case_version:              # Case version string
common_materials:          # task_contract, candidate_summary, materials, evidence_refs
common_materials_sha256:   # Canonical hash (identical across arms for same case)
arm_overlay:               # Arm-specific addition only
response_contract:         # Shared response format
packet_sha256:             # Canonical hash of packet body
```

---

## 7. Observation Schema

Each observation (`nexus.epistemic_benchmark_observation.v0`):

```yaml
schema:
observation_id:            # Unique
benchmark_run_id:
arm:
case_alias:                # Must match a valid packet

evaluator:
  evaluator_id:
  provider:                # "synthetic-test" for fixtures
  model_id:                # "deterministic-fixture" for fixtures
  prompt_version:

decision:                  # ACCEPT | REJECT | BLOCK
detected_defect_ids:       # Reviewer-assigned IDs (oracle scoring uses known_defect_ids)
cited_evidence_refs:       # Must exist in packet
rationale_summary:         # ≤ 2,000 characters
confidence:                # 0–100 integer or null (bool rejected)

execution:
  started_at:              # Timezone-aware ISO-8601
  completed_at:            # Timezone-aware ISO-8601
  duration_seconds:        # ≥ 0
  input_tokens:            # null or non-negative
  output_tokens:           # null or non-negative
  cost_usd:                # null or non-negative

skipped_checks:
observation_sha256:        # Recomputable
```

Rules:
- No Chain of Thought stored
- Missing observations are never scored as correct
- Import does not read oracle or compute correctness

---

## 8. Metrics Definitions

All metrics are **descriptive only**.

| Metric | Definition |
|--------|-----------|
| `decision_accuracy` | `obs.decision == oracle.oracle_decision` |
| `false_acceptance_rate` | On DEFECTIVE cases: rate of ACCEPT decisions |
| `false_rejection_rate` | On CLEAN cases: rate of REJECT decisions |
| `appropriate_abstention_rate` | On INDETERMINATE cases: rate of BLOCK decisions |
| `over_abstention_rate` | On non-INDETERMINATE cases: rate of BLOCK decisions |
| `defect_detection_recall` | Detected known defect IDs / all known defect IDs (DEFECTIVE only) |
| `critical_defect_detection_recall` | Same but only for CRITICAL severity defects |
| `high_defect_detection_recall` | Same but only for HIGH severity defects |
| `evidence_reference_validity_rate` | Valid cited refs / all cited refs |
| `mean_confidence` | Mean of confidence values (null excluded) |
| `brier_score` | `(correctness − confidence/100)²` averaged over observations with confidence |
| `brier_calibration_sample_count` | Number of observations contributing to Brier |
| `median_duration_seconds` | Median of `execution.duration_seconds` |
| `p95_duration_seconds` | 95th percentile of durations |
| `total_input_tokens` | Sum |
| `total_output_tokens` | Sum |
| `total_cost_usd` | Sum (null if no costs provided) |
| `decision_agreement` | For multi-reviewer cases: `max_decision_count / total` averaged over such cases |

Paired comparisons (B vs A, C vs B, C vs A) report deltas. **Positive delta ≠ improvement**.

---

## 9. Missing-Data Policy

Missing, invalid, or skipped observations are **never** counted as correct decisions.

The report always shows, per arm:
- `assigned_cases`: total corpus cases
- `observed_cases`: cases with at least one observation
- `valid_observations`: count of schema-valid observations
- `invalid_observations`: count of parse/validation failures
- `missing_cases`: `assigned_cases − observed_cases`

If any arm has `completion_rate < 80%`, the Markdown report begins with:

```
INCOMPLETE BENCHMARK COVERAGE
```

---

## 10. CLI Examples

```bash
# Validate corpus
python -m nexus.research.epistemic_benchmark.cli validate-corpus

# Prepare a run
python -m nexus.research.epistemic_benchmark.cli prepare-run \
  --output /tmp/ebr-run-001 \
  --seed 20260802

# Import a reviewer observation
python -m nexus.research.epistemic_benchmark.cli import-observation \
  --run-dir /tmp/ebr-run-001 \
  --input /path/to/observation.json

# Evaluate benchmark
python -m nexus.research.epistemic_benchmark.cli evaluate \
  --run-dir /tmp/ebr-run-001 \
  --json-output /tmp/report.json \
  --markdown-output /tmp/report.md

# Verify report
python -m nexus.research.epistemic_benchmark.cli verify-report \
  --run-dir /tmp/ebr-run-001 \
  --input /tmp/report.json
```

Success statuses: `CORPUS_VALID`, `RUN_PREPARED`, `OBSERVATION_IMPORTED`, `BENCHMARK_EVALUATED`, `BENCHMARK_REPORT_VERIFIED`

---

## 11. Model Execution Not in Scope

This task builds the **harness only**. No model is called by the benchmark.

To run a real benchmark:
1. Prepare a run with `prepare-run`
2. Distribute packets to reviewers (human or model)
3. Collect reviewer `observation.json` files
4. Import with `import-observation`
5. Evaluate with `evaluate`
6. Verify with `verify-report`

---

## 12. Limitations

- Synthetic corpus only — no real acceptance decisions
- No live model calls performed by harness
- Model/provider results depend on imported observations
- Local repository access can defeat oracle isolation if packet boundaries are ignored
- Small corpus (18 cases)
- No external validity claim
- No regulated-domain claim
- Descriptive metrics only — no statistical inference

---

## 13. Claim Ceiling

> This benchmark report summarizes observations collected under versioned synthetic review protocols. It does not establish statistical significance, general research-quality improvement, production readiness, or that an epistemic ledger is necessary.

---

## 14. Next Gate

`ERB-01-INDEPENDENT-ACCEPTANCE`

Requirements for the next gate:
- Independent reviewer examines the Candidate commit
- Confirms oracle isolation, fairness invariants, and test passage
- Real model observations may be collected and evaluated under this benchmark
- No claims may be upgraded until ERB-01 accepts the harness

**Do not begin real model benchmarking before ERB-01 acceptance.**
