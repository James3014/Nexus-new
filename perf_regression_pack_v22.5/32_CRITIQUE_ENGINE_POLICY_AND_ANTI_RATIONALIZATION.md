# 32_CRITIQUE_ENGINE_POLICY_AND_ANTI__RATIONALIZATION.md

**Purpose**: Anti-Rationalization Policy for Nexus v23.5.
**Source**: 32_CRITIQUE_POLICY (Draft)
**Commit**: v23.5-alpha-spec-032
**Generated_at**: 2026-04-08 01:25

---

## 🏗️ Enforcement Rules
- **Anti-Rationalization**: Explanations justifying unsafe or out-of-scope tasks will be blocked.
- **Intent Pre-scan**: Every tool call MUST be justified by evidence before execution.

---

# 33_SESSION_DISTILLATION_AND_HANDOFF_PROTOCOL.md

**Purpose**: Session Life-cycle and Distillation Strategy.
**Source**: 33_DISTILL_PROTOCOL (Draft)
**Commit**: v23.5-alpha-spec-033
**Generated_at**: 2026-04-08 01:26

---

## 🏗️ Reset Sequence
- **Trigger**: Input context > 85%.
- **Payload**: Manifest / Lineage / Evidence / Constraints.
- **Handoff**: Arweave sync on session end.

---

# 34_TOOL_EXPOSURE_BUDGET_AND_CONTEXT_POLICY.md

**Purpose**: Context Hygiene and Exposure Rules.
**Source**: 34_TOOL_BUDGET (Draft)
**Commit**: v23.5-alpha-spec-034
**Generated_at**: 2026-04-08 01:27

---

## 🏗️ Budgeting Rules
- **Max Exposed Tools**: Q1: 5 / Q2: 15 / Q3: 30.
- **Progressive Disclosure**: Dynamic tool disclosure based on the current active task step.

---

# 35_V23_5_ROLLOUT_GATES_AND_BENCHMARKS.md

**Purpose**: Certification Gates for v23.5.
**Source**: 35_ROLLOUT_GATES (Draft)
**Commit**: v23.5-alpha-spec-035
**Generated_at**: 2026-04-08 01:28

---

## ✅ Rollout Thresholds
- **Evidence Integrity**: 100% manifest pass.
- **Divergence Rollback**: Critical violation triggers auto-rollback to v22 Stable.
- **Target Hit-Rate**: > 98% Correct Domain routing.
