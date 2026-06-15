# Policy Baseline Manifest (v1.0.0)

This manifest serves as the formal baseline audit record for all active governance policies under the Nexus local collaboration framework.

---

## 📋 Auditable Governance Policy Matrix

### 1. 3B Limited Assist Policy
- **Classification**: Code-backed
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: N/A
- **Primary File(s)**: [experimental_gate.py](file:///Users/jameschen/Workspace/nexus/nexus/gate/experimental_gate.py#L71)
- **Test / Report Entry Point**: [test_experimental_gate.py](file:///Users/jameschen/Workspace/nexus/tests/gates/test_experimental_gate.py)
- **Rollback Drill Status**: Verified. Under `NEXUS_SHADOW_ADVISOR_ENABLED=false`, execution seamlessly reverts to Baseline Python/Rules.

### 2. 1.5B Optional Hint Policy
- **Classification**: Code-backed
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: Gatekeeper V2 Schema Hints
- **Primary File(s)**: [experimental_gate.py](file:///Users/jameschen/Workspace/nexus/nexus/gate/experimental_gate.py#L12)
- **Test / Report Entry Point**: [test_experimental_gate.py](file:///Users/jameschen/Workspace/nexus/tests/gates/test_experimental_gate.py#L41)
- **Rollback Drill Status**: Verified. Under `NEXUS_GATEKEEPER_15B_ENABLED=0`, skips pre-screening and default checks apply.

### 3. 7B/14B Whitelist Deliberation Policy
- **Classification**: Code-backed
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: N/A
- **Primary File(s)**: [local_deliberation_lane.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_deliberation_lane.py)
- **Test / Report Entry Point**: [test_local_deliberation_lane.py](file:///Users/jameschen/Workspace/nexus/tests/unit/test_local_deliberation_lane.py)
- **Rollback Drill Status**: Verified. Deliberation requests outside whitelisted task families (`high-uncertainty / repair-review / research-brief`) fall back to static rule path.

### 4. No Default Router Replacement
- **Classification**: Spec-backed
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: N/A
- **Primary File(s)**: [limited_assisted_adoption_dossier.md](file:///Users/jameschen/Workspace/nexus/docs/reports/limited_assisted_adoption_dossier.md#L39)
- **Test / Report Entry Point**: [limited_mount_observation_summary.md](file:///Users/jameschen/Workspace/nexus/docs/reports/limited_mount_observation_summary.md#L50)
- **Rollback Drill Status**: Verified. All experimental endpoints are gated behind Feature Flags. Default routing remains statically ruled.

### 5. No Verifier / Claim Gate / Delivery Gate Replacement
- **Classification**: Spec-backed
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: N/A
- **Primary File(s)**: [gate_judge.py](file:///Users/jameschen/Workspace/nexus/nexus/gate/gate_judge.py)
- **Test / Report Entry Point**: [test_experimental_gate.py](file:///Users/jameschen/Workspace/nexus/tests/gates/test_experimental_gate.py)
- **Rollback Drill Status**: Immutable Core. Verifiers remain core Python/Rust static rule checks.

### 6. No Policy Auto-Mutation
- **Classification**: Spec-backed
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: N/A
- **Primary File(s)**: [limited_assisted_adoption_dossier.md](file:///Users/jameschen/Workspace/nexus/docs/reports/limited_assisted_adoption_dossier.md#L41)
- **Test / Report Entry Point**: [policy-baseline-manifest.v1.md](file:///Users/jameschen/Workspace/nexus/docs/reports/policy-baseline-manifest.v1.md)
- **Rollback Drill Status**: Strictly Blocked. Automated modification scripts do not exist in the codebase. Static configuration requires manual git commit.

### 7. Mandatory Feature Flag / Fallback / Rollback
- **Classification**: Code-backed
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: N/A
- **Primary File(s)**: [experimental_gate.py](file:///Users/jameschen/Workspace/nexus/nexus/gate/experimental_gate.py#L112)
- **Test / Report Entry Point**: [policy-rollback-drill-matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/policy-rollback-drill-matrix.md)
- **Rollback Drill Status**: Drilled & Documented. Full 27 policy fallback coverage verified.

### 8. Observation Cycle Gate Requirement
- **Classification**: Historical
- **Commit SHA**: `edf13b86dd39d322d77477a40afd68d47bea7cf6`
- **Schema Version**: N/A
- **Primary File(s)**: [limited_mount_observation_summary.md](file:///Users/jameschen/Workspace/nexus/docs/reports/limited_mount_observation_summary.md)
- **Test / Report Entry Point**: [run_observation_cycle_01.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/run_observation_cycle_01.py), [run_observation_cycle_02.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/run_observation_cycle_02.py), [run_observation_cycle_03.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/run_observation_cycle_03.py)
- **Rollback Drill Status**: Verified. Cumulative 90 tasks run across 3 cycles confirm 0% trust mismatch.
