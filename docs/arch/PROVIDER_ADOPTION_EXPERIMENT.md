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
- **Provenance Classification:** Distinguishes `FIXTURE_COHORT`, `BENCHMARK_COHORT`, and `PHYSICAL_HISTORICAL_COHORT`.
- **Ground Truth Readiness:** If ground truth is incomplete or unverified, evaluation halts with `GROUND_TRUTH_NOT_READY`.
- **Single Run Identity:** Generates a single stable `run_id` for the entire run. All case receipts bind to this exact `run_id`.
- **Active Stop Condition Monitoring:** Evaluates consecutive failures, error rate, and safety timeouts after every case. If a threshold is crossed, halts immediately with `STOPPED_BY_CONDITION`.

### G4 — Operational Metrics
- Schema: `nexus.provider_experiment.operational_metrics.v1`.
- Aggregates p50/p95 latency, min/max/mean latency, throughput (rps), error rates, and cold-start overhead.
- **Offline Verification:** `offline_status` is marked `VERIFIED_OFFLINE` only if backed by physical offline execution evidence. Otherwise defaults to `UNKNOWN` or `NOT_EVALUATED`.

### G5 — Failure Behavior Matrix
- Schema: `nexus.provider_experiment.failure_matrix.v1`.
- Evaluates canonical failure classes (`AUTH_ERROR`, `RATE_LIMIT`, `PROVIDER_TIMEOUT`, `PROCESS_CRASH`, etc.).
- **Contract vs Observation:** Separates expected fail-closed behavior (`failure_contract`) from physical observed evidence (`failure_observation`). Expected rules are never reported as candidate evidence.
- **Retry Invariant:** `OUTCOME_UNKNOWN != RETRY_PERMISSION`.

### G6 — Admission Recommendation
- Schema: `nexus.provider_experiment.recommendation.v1`.
- Fixed verdict: `ADMISSION_RECOMMENDATION_ONLY_NO_AUTHORITY_GRANTED`.
- Maps recommendations directly to Nexus Workforce Admission vocabulary:
  - Autonomy Levels: `L0`, `L0.25`, `L0.5`, `L1`, `L2`, `L2+`, `L3` (from `nexus/contracts/workforce_admission.py`).
  - Workforce States: `EXPERIMENT_ONLY`, `LOCAL_CONDITIONAL`, `REGISTERED_CONDITIONAL`, `REGISTERED_BLOCKED` (from `nexus/config/model_workforce.yaml`).
  - Roles: `simple_extraction`, `read_only_schema_candidate`, `bounded_experiment`, etc.
- **Strict Clamping:** Recommended autonomy can never exceed the contract's `claim_ceiling`.

---

## 3. False-Green Defenses and Verifier Invariants

The framework enforces six mandatory false-green defenses:
1. **Offline Status Invariant (6.1):** `apple-fm` or local models never automatically receive `VERIFIED_OFFLINE` without physical offline network tests.
2. **Capability Probe Invariant (6.2):** Absence of blockers does not imply `SUPPORTED`. Every supported capability must have physical execution proof.
3. **Failure Observation Invariant (6.3):** Pre-declared expected behavior cannot be claimed as candidate evidence. `all_fail_closed_observed` is `None` unless physically exercised.
4. **Active Stop Condition Invariant (6.4):** When failure thresholds are hit, remaining cases are immediately aborted. Subsequent cases do not consume execution time.
5. **Cohort Provenance Invariant (6.5):** Synthetic test fixtures cannot claim historical receipt status. Unready promotion ground truth yields `GROUND_TRUTH_NOT_READY`.
6. **Single Run Identity Invariant (6.6):** All case evaluations share a single immutable `run_id`.

---

## 4. Reference Candidate: Apple Foundation Models Pilot (V1)

Apple Foundation Models is evaluated as the reference pilot candidate (`APPLE_FM_LOCAL_PROVIDER_PILOT_V1`):
- **Executable:** `/usr/bin/fm`.
- **Environment Blocker:** If the host CLI reports license not agreed (`fm license --status` exits with code 69 or outputs `Not agreed`), the adapter marks status as `BLOCKED_BY_ENVIRONMENT` with blocker code `APPLE_FM_LICENSE_NOT_AGREED`.
- **License Boundary:** Coding agents must **never** execute `sudo fm license` or accept legal agreements autonomously. License review is reserved strictly for the human Owner.
- **Admittance Boundary:** Apple FM remains strictly in pre-three-arm qualification discovery via `scripts/bench/experimental/run_provider_adoption_experiment.py`. It is NOT enrolled in `nexus/config/model_three_arm_matrix.yaml` until physical benchmark execution is supported and proven, and is NOT admitted into `nexus/config/model_workforce.yaml`.
- **Next Gate:** `INDEPENDENT_REVIEW_OF_PROVIDER_ADOPTION_CANDIDATE_R2`.
