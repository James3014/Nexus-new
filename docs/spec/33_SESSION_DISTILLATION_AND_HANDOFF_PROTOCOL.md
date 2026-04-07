# 33_SESSION_DISTILLATION_AND_HANDOFF_PROTOCOL.md

**Purpose**: Formalize the mechanism for session distillation and context reset to maintain high performance and context clarity during long-running swarm operations.
**Source**: nexus/services/memory_repository.py (Ref), session_artifacts/ (Ref)
**Commit**: v23.5-alpha-spec-033
**Generated_at**: 2026-04-08 01:10 (System Local)

---

## 1. Token Budget Trigger
- **Threshold**: Session MUST trigger distillation when the input context exceeds **85% of the model's max context window** (Targeting 128k/200k context windows).
- **Grace Period**: 5 messages before a mandatory reset.

## 2. Distill Payload Schema (The "Essence")
The distilled payload MUST contain:
- **`manifest`**: Current project state and goal.
- **`lineage`**: Chain of accomplishments.
- **`high_signal_evidence`**: Final findings only.
- **`active_constraints`**: Current policy/domain restrictions.

## 3. Reset Sequence & Handoff
1. **Archive**: Upload the full state to **Arweave** (Boundary: Session-End).
2. **Distill**: Generate the "Essence" payload.
3. **Reset**: Wipe the ephemeral session memory.
4. **Restore**: Re-inject the "Essence" payload into a fresh session.

## 4. Safety Constraints
- **Lossless Handoff**: The new session MUST verify its reachability to the previous evidence-IDs.
- **Failure**: On distillation failure, the session is **Frozen** for human manual review.

---

# 34_TOOL_EXPOSURE_BUDGET_AND_CONTEXT_POLICY.md

**Purpose**: Define strict limits on tool exposure and context usage to prevent "Context Junk" and minimize the surface area for rationalization/misuse.
**Source**: nexus/router/exposure.py (Ref), tactical_map.json (Ref)
**Commit**: v23.5-alpha-spec-034
**Generated_at**: 2026-04-08 01:12 (System Local)

---

## 1. Max Exposed Tools by Stage
Exposure is capped to minimize "noise":
- **Research Phase**: Max 30 tools (Observation focused).
- **Action Phase**: Max 15 tools (Execution focused).
- **Critical Phase (Q1)**: Max 5 tools (Precision focused).

## 2. Domain-First Exposure Rule
Tools from **Current Domain** take priority. Cross-domain promotion criteria (e.g., Q3 -> Q2) require an **Escalation Event** log.

## 3. Progressive Disclosure Rule
Only disclose tools that match the CURRENT task step. If the task shifts, the Router MUST **Narrow** the toolset dynamically.

## 4. Context Overflow Prevention Policy
- **Summarization Hooks**: Automatic summarization of long tool outputs (e.g., directory listings > 100 lines).
- **Emergency Narrowing**: If token costs spike > 200% within 3 turns, auto-enforce **Domain Lockdown (Q1 Only)**.

---

# 35_V23_5_ROLLOUT_GATES_AND_BENCHMARKS.md

**Purpose**: Establish rigorous acceptance criteria and performance targets for the v23.5 "Brain-Armor Fusion" release.
**Source**: benchmarks/performance_baseline.md (Ref), tests/validation_v23_5.py (Ref)
**Commit**: v23.5-alpha-spec-035
**Generated_at**: 2026-04-08 01:15 (System Local)

---

## 1. Target Benchmarks
| Metric | Baseline (v22) | Target (v23.5) |
| :--- | :--- | :--- |
| **Tool Exposure reduction** | 100% (Full) | < 30% per task step |
| **Router Hit-Rate (Correct Domain)** | 85% | > 98% |
| **Cross-domain Misuse Rate** | 5% | **0% (Hard-Block)** |
| **Critique Precision** | 70% | > 92% |
| **Handoff Recovery Rate** | 90% | 100% (Verifiable) |

## 2. Release Gates & Staged Rollout
1. **Gate A (Sandbox)**: 100% pass on synthetic "misuse" scenarios.
2. **Gate B (Staging)**: 0 critical "Rationalization" incidents in a 24h swarm run.
3. **Gate C (Production)**: Evidence-Integrity score > 0.99 for all sessions.

## 4. Rollback Triggers (P0)
- **Trigger**: Any **Quadrant I (Critical Core)** violation that bypasses the firewall.
- **Trigger**: Any session drift resulting in a **Corrupted Evidence Archive**.
- **Action**: Immediate revert to **Version: 23.1-STABLE**.

## 5. Telemetry Oversight
All v23.5 sessions MUST report to the **Nexus Status Dashboard** using the new `FusionCompliance` metric suite.
