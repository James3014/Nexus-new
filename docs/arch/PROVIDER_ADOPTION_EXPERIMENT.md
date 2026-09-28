# Provider Adoption Experiment Framework (V1)

**Document Schema:** `nexus.provider_experiment.architecture.v1`
**Owner:** James Chen / Nexus Architecture
**Canonical Repository:** `James3014/Nexus-new`
**Authority Boundary:** Calibration and Evidence Plane only. Grants **zero** routing, admission, or mutation authority.

---

## 1. Architectural Authority and Ownership

The **Provider Adoption Experiment Framework** (`PROVIDER_ADOPTION_EXPERIMENT_V1`) provides a universal, repeatable, and falsification-resistant mechanism for evaluating new LLM providers and models before admission into the Nexus model workforce.

### 1.1 Canonical Ownership vs Execution Substrate
- **Canonical Owner:** `James3014/Nexus-new`.
  Nexus is the sole System of Record (SSOT) for workforce configuration (`nexus/config/model_workforce.yaml`), calibration matrices (`nexus/config/model_three_arm_matrix.yaml`), CapabilityPlanner route policies, and Workforce Admission contracts (`nexus/contracts/workforce_admission.py`).
- **External Substrate Optionality:** `James3014/devspace`.
  DevSpace MAY be used as an optional external host/control/execution transport where explicitly selected.
  Crucial boundaries:
  - DevSpace is NOT a required substrate for Local Models.
  - Apple FM can be called directly by the Nexus calibration host via `/usr/bin/fm`.
  - Ollama can be executed by its own local provider backend.
  - MLX can have its own explicit backend.
  - Local model execution does not depend on DevSpace.
  - DevSpace does not own provider calibration, Workforce, Local Armor, or local model lifecycle.
  - Operating a Mac via DevSpace (e.g. from ChatGPT) does NOT make DevSpace an architectural dependency of Nexus local models.

### 1.2 Separation of Concerns
```text
CapabilityPlanner
      │ (sole route selection authority)
      ▼
Workforce Admission
      │ (constrains eligible workers by policy)
      ▼
Execution Backend
      ├── Apple FM (/usr/bin/fm)
      ├── Ollama (HTTP)
      ├── MLX (Local)
      └── Cloud Providers (Codex, Gemini, Grok)

═════════════════════════════════════════════════════════════
Calibration & Evidence Plane (Provider Adoption Experiment)
      │
      ├── G0: Immutable Contract (Bound to SHA-256)
      ├── G1: Physical Host & Binary Identity
      ├── G2: Capability Probes (False-Green Protected)
      ├── G3: Frozen Cohort Evaluation (Single Run ID, Leakage Defense)
      ├── G4: Operational Metrics (Latency, Throughput, Cost)
      ├── G5: Failure Matrix (Expected Contract vs Physical Observation)
      └── G6: Advisory Admission Recommendation
               │
               ▼
   Owner + Workforce Admission Authority (Human/Policy Gate)
```

The experiment framework **never** grants admission, routes traffic, modifies code, or merges PRs. Its G6 output is strictly an `ADMISSION_RECOMMENDATION_ONLY_NO_AUTHORITY_GRANTED`.

---

## 2. The G0–G6 Lifecycle Gates

The evaluation lifecycle progresses through seven sequential gates. No gate may be skipped:

```text
DRAFT → G0 CONTRACT_FROZEN → G1 IDENTITY_INSPECTED → G2 CAPABILITY_PROBED
      → G3 COHORT_EVALUATED → G4 OPERATIONAL_EVALUATED → G5 FAILURE_EVALUATED
      → G6 RECOMMENDATION_READY
```

### G0 — Experiment Contract
- Schema: `nexus.provider_experiment.contract.v1`.
- Fully machine-readable and hashed via `canonical_json_hash`.
- Declares candidate identity, allowed/forbidden capabilities, dataset hashes, thresholds, stop conditions, and claim ceiling.
- **Fail-Closed Boundary Enforcement:** Strictly rejects any contract that attempts to grant `routing_authority`, `acceptance_authority`, `write_permission`, `process_permission`, or `network_permission`.
- **Capability Consistency:** Rejects any overlap between `allowed_capabilities` and `forbidden_capabilities`.

### G1 — Physical Identity
- Schema: `nexus.provider_experiment.physical_identity.v1`.
- Inspects concrete physical hardware, OS version, kernel release, CPU model, runtime executable path, binary SHA-256, and runtime version.
- **Honest Observation:** Unobservable attributes remain `UNKNOWN`. Never fills expected facts into observed fields.
- **Identity Drift Evaluation:** Classifies drift as `CURRENT`, `STALE` (OS/adapter update), or `REQUALIFICATION_REQUIRED` (model, provider, or runtime binary change).

### G2 — Capability Matrix
- Schema: `nexus.provider_experiment.capability_matrix.v1`.
- Evaluates canonical capabilities (`CAP-001` through `CAP-011`): plain text completion, structured JSON, schema compliance, classification, extraction, summarization, streaming, tool calling, long-context, offline execution, and repeatability.
- **False-Green Defense:** Command exit code `0` alone never equals `SUPPORTED`. Output must be non-empty and satisfy semantic validation. Unprobed capabilities remain `NOT_EVALUATED`.

### G3 — Frozen Quality Cohort
- Schema: `nexus.provider_experiment.cohort.v1`.
- Separates cohort input hash (`cohort_sha256`) from ground truth hash (`ground_truth_sha256`).
- **Dataset Cross-Binding:** Verifies strict binding between `ExperimentContract.dataset` and `FrozenCohort` (id, revisions, hashes, type, readiness).
- **Leakage Defense:** Audits cohort for prompt leaks prior to candidate execution; detected leaks fail closed. Audit status accurately records `PASSED`, `FAILED`, or `NOT_EVALUATED`.
- **Provenance Classification:** Distinguishes `FIXTURE_COHORT`, `BENCHMARK_COHORT`, and `PHYSICAL_HISTORICAL_COHORT`.
- **Ground Truth Readiness:** If ground truth is incomplete or unverified, evaluation halts with `GROUND_TRUTH_NOT_READY`.
- **Single Run Identity:** Generates a single stable `run_id` for the entire run. All case receipts bind to this exact `run_id`.
- **Active Stop Condition Monitoring:** Evaluates consecutive failures, error rate, and safety timeouts after every case. If a threshold is crossed, halts immediately with `STOPPED_BY_CONDITION`.
- **Evidence Level Ceiling Enforcement:** Mock or simulated evidence must never masquerade as physical evidence. Case evaluations are clamped to the adapter's declared maximum supportable evidence level ceiling (`min(requested, adapter_ceiling)` under ordering `FIXTURE < SIMULATED < PHYSICAL`).

### G4 — Operational Metrics
- Schema: `nexus.provider_experiment.operational_metrics.v1`.
- Aggregates p50/p95 latency, min/max/mean latency, throughput (rps), error rates, and cold-start overhead.
- **Contract Enforcement:** Contract minimum throughput (`min_throughput_rps`) and latency limits actively govern admission recommendation.
- **Offline Verification:** `offline_status` is marked `VERIFIED_OFFLINE` only if backed by physical offline execution evidence. Otherwise defaults to `UNKNOWN` or `NOT_EVALUATED`.

### Baseline Calibration and Comparative Evidence (Optional)
- Schema: `nexus.provider_experiment.baseline_evaluation.v1`.
- **Optional Execution:**
  - If `contract.baseline` is `None`: status is `NOT_REQUESTED`.
  - If `contract.baseline` is declared but `baseline_adapter` is `None`: status is `NOT_EVALUATED` (with reason recorded). Candidate executes standalone.
- **Physical Identity Verification:** Before any cohort case execution, the baseline adapter's physical identity (`provider_id`, `model_id`, `transport`) is inspected. Any discrepancy with `contract.baseline` yields `IDENTITY_MISMATCH` with zero case execution and comparison `NOT_AVAILABLE`.
- **Environment Blockers:** If the baseline adapter reports environment blocked, status is marked `UNAVAILABLE` with the exact blocker reason. No fake measurement is made.
- **Cohort Parity:** If physical identity matches and environment is clear, baseline executes the SAME exact `FrozenCohort` cases with identical prompt digests and identical grading semantics (`ground_truth`, `acceptable_variants`, `forbidden_outputs`, `schema_valid`).
- **Independent Execution Identity & Evidence Ceiling:** Baseline case evaluations are recorded under a distinct, stable `baseline_run_id`, bound to the baseline's physical identity digest, and resolved independently to its own adapter evidence ceiling (e.g. a simulated baseline remains `SIMULATED` even during a `PHYSICAL` candidate run).
- **Stop Conditions:** Baseline enforces stop conditions during cohort evaluation. Early stop sets status to `STOPPED_BY_CONDITION` and disables comparison (`NOT_AVAILABLE`).
- **Comparative Evidence:** Factual metric deltas (accuracy, error rate, p50/p95 latency, throughput) are computed only when `baseline_status == EVALUATED` and candidate cohort was fully evaluated. If baseline was not evaluated or stopped early, comparison status is explicitly `NOT_AVAILABLE`.
- **Baseline Fault Containment:** Baseline adapter exceptions (identity probe, environment check, case execution) are strictly contained inside baseline evaluation. Baseline status is marked `UNAVAILABLE` with bounded deterministic error text and comparison is marked `NOT_AVAILABLE`. Candidate receipt, operational metrics, state history, and G6 admission recommendation survive completely unaltered.
- **Zero Candidate Authority Alteration:** Baseline evaluation is purely descriptive calibration evidence. It does not run G5 fault injection, does not mutate candidate lifecycle state, and never promotes, demotes, or alters candidate G6 admission recommendation.

### G5 — Failure Behavior Matrix
- Schema: `nexus.provider_experiment.failure_matrix.v1`.
- Evaluates canonical failure classes (`AUTH_ERROR`, `RATE_LIMIT`, `PROVIDER_TIMEOUT`, `PROCESS_CRASH`, etc.).
- **Contract vs Observation:** Separates expected fail-closed behavior (`failure_contract`) from physical observed evidence (`failure_observation`). Expected rules are never reported as candidate evidence.
- **Terminal Stop Protection:** When a quality/safety stop condition is triggered, G5 active fault injection is skipped, returning a `NOT_EVALUATED` observation matrix.
- **Retry Invariant:** `OUTCOME_UNKNOWN != RETRY_PERMISSION`.

### G6 — Admission Recommendation
- Schema: `nexus.provider_experiment.recommendation.v1`.
- Fixed verdict: `ADMISSION_RECOMMENDATION_ONLY_NO_AUTHORITY_GRANTED`.
- **Blocker Categorization:** Strictly distinguishes `ENVIRONMENT`, `DATA/COHORT`, and `EVALUATION_STOP` blocker categories.
- Maps recommendations directly to Nexus Workforce Admission vocabulary:
  - Autonomy Levels: `L0`, `L0.25`, `L0.5`, `L1`, `L2`, `L2+`, `L3` (from `nexus/contracts/workforce_admission.py`).
  - Workforce States: `EXPERIMENT_ONLY`, `LOCAL_CONDITIONAL`, `REGISTERED_CONDITIONAL`, `REGISTERED_BLOCKED` (from `nexus/config/model_workforce.yaml`).
  - Roles: `simple_extraction`, `read_only_schema_candidate`, `bounded_experiment`, etc.
- **Strict Clamping:** Recommended autonomy can never exceed the contract's `claim_ceiling`.

---

## 3. False-Green Defenses and Verifier Invariants

The framework enforces eight mandatory false-green defenses:
1. **Offline Status Invariant (6.1):** `apple-fm` or local models never automatically receive `VERIFIED_OFFLINE` without physical offline network tests.
2. **Capability Probe Invariant (6.2):** Absence of blockers does not imply `SUPPORTED`. Every supported capability must have physical execution proof.
3. **Failure Observation Invariant (6.3):** Pre-declared expected behavior cannot be claimed as candidate evidence. `all_fail_closed_observed` is `None` unless physically exercised.
4. **Active Stop Condition Invariant (6.4):** When failure thresholds are hit, remaining cases are immediately aborted. Subsequent cases do not consume execution time.
5. **Cohort Provenance Invariant (6.5):** Synthetic test fixtures cannot claim historical receipt status. Unready promotion ground truth yields `GROUND_TRUTH_NOT_READY`.
6. **Single Run Identity Invariant (6.6):** All case evaluations share a single immutable `run_id`.
7. **Baseline Calibration Parity Invariant (6.7):** Baseline evaluation must execute the exact same frozen cohort cases and grading rules as candidate, bind a separate stable `baseline_run_id`, never alter candidate G6 authority, contain adapter exceptions cleanly with `UNAVAILABLE` status, and fail closed to `NOT_AVAILABLE` comparison whenever baseline or candidate execution is incomplete, mismatched, or blocked.
8. **Evidence Level Ceiling Invariant (6.8):** Mock, fixture, or simulated evidence must never masquerade as `PHYSICAL` evidence. Each adapter declares its maximum supportable evidence level ceiling (`CandidateAdapter` default `SIMULATED`, `AppleFMCandidateAdapter` `PHYSICAL`). All `SimulatedCandidateAdapter` instances and subclasses are hard-capped to `SIMULATED`. Caller requested evidence level can only narrow (underclaim), never escalate above the adapter ceiling (`min(requested, ceiling)` with `FIXTURE < SIMULATED < PHYSICAL`). Candidate and baseline evidence levels resolve independently.

---

## 4. Reference Candidate: Apple Foundation Models Pilot (V3)

Apple Foundation Models is evaluated as a bounded local reference candidate through `scripts/bench/experimental/run_provider_adoption_experiment.py --candidate apple-fm`:
- **Executable:** `/usr/bin/fm`; the adapter uses the current `fm respond` command surface and requests deterministic `--no-stream --greedy` probes where exact scoring is required.
- **Environment Blocker:** If the host CLI reports license not agreed (`fm license --status` exits with code 69 or outputs `Not agreed`), the adapter marks status as `BLOCKED_BY_ENVIRONMENT` with blocker code `APPLE_FM_LICENSE_NOT_AGREED`.
- **License Boundary:** Coding agents must **never** execute `sudo fm license` or accept legal agreements autonomously. License review is reserved strictly for the human Owner.
- **Frozen V3 Fixture:** The Apple runner uses `COHORT-APPLE-FM-DETERMINISTIC-V3`, an eight-case deterministic classification/literal-extraction fixture with separately bound cohort and ground-truth hashes. Free-form summarization is deliberately excluded from this gate because the generic evaluator uses deterministic grading rather than an uncalibrated semantic judge.
- **Physical Capability Probes:** `CAP-001` plain text, `CAP-002` structured JSON, `CAP-004` classification, and `CAP-005` extraction have objective physical probe implementations. Structured JSON uses a schema generated by the Apple CLI (`fm schema object`) and exact parsed values; command exit zero alone is never sufficient.
- **Evidence Identity:** Apple FM declares a `PHYSICAL` evidence ceiling, while callers may only underclaim. Observation timestamp and later offline/network observations do not mint a new execution identity; provider/model/transport/host/runtime/source identity remain bound.
- **Unproven Capabilities:** `CAP-003` generic schema-constrained behavior, `CAP-006` free-form summarization, `CAP-010` offline execution, failure-injection behavior, and network independence remain `NOT_EVALUATED`/`UNKNOWN` until separately proven.
- **Claim Ceiling:** The V3 pilot contract caps advisory autonomy at `L0.5`. A physical pilot result is calibration evidence only; it does not change CapabilityPlanner routing, Workforce Admission, runtime provider registration, release, or production state.
- **Admittance Boundary:** Apple FM remains pre-three-arm qualification evidence. It is NOT enrolled in `nexus/config/model_three_arm_matrix.yaml` and is NOT admitted into `nexus/config/model_workforce.yaml` by this pilot.
- **Promotion Review Delta (2026-09-28):** A fresh 30-case private holdout produced 29/30 exact first-pass results twice. The single repeated defect confused total attempt count with retry count. A separate eight-case adjacent failure-family probe scored 7/8 and reproduced the same `attempt` vs `retry` semantic error. Under the pre-registered zero-error promotion gate this remains a failed promotion attempt; the prior bounded L0.5 evidence is not erased.
- **Process-Level Offline Evidence:** The same macOS `sandbox-exec` profile with `deny network*` blocked a curl control while `fm` inference and a five-case structured-output holdout continued to succeed. This is useful physical evidence, but `CAP-010` remains `NOT_EVALUATED` until the offline probe is integrated into the formal capability adapter and receipt path.
- **Experimental Read-Only Pool:** `apple_fm_worker_pool.py` is an experiment-only batch executor for classification, literal extraction, and JSON-schema-constrained output. It defaults to concurrency 2 and hard-caps at 4; known risky semantic tags including `retry_attempt_semantics`, architecture judgment, state-transition reasoning, and mutation are rejected before execution. Automatic fallback is disabled; failures return `needs_escalation` only.
- **Concurrency Evidence (M5 Pro / 64 GB):** Three 16-request physical rounds at each pool size all passed exactly under process-level network denial. Median throughput was 3.542 rps at concurrency 1, 5.351 rps at concurrency 2, and 6.209 rps at concurrency 4. Median p50 latency was 281 ms, 356 ms, and 598 ms respectively. Therefore concurrency 2 is the latency-balanced default; concurrency 4 is an explicit bulk/burst option, not an automatic scaling target.
- **Authority Boundary:** The worker pool is calibration infrastructure only. It does not register Apple FM in `model_workforce.yaml`, does not alter CapabilityPlanner routing, does not grant Workforce Admission, does not auto-dispatch cloud fallback, and does not create mutation, acceptance, merge, release, or production authority.
- **Next Gate:** independent review of the exact experimental worker-pool Candidate and its physical evidence. Any Workforce or routing integration is a separate governed decision.
