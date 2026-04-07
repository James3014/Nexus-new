# 44_RETRIEVAL_REUSE_ATTRIBUTION_REPORT.md

**Purpose**: Provide formal attribution of how retrieval reuse directly impacts and improves the Nexus decision-making processes.
**Source**: nexus/research/wisdom_distiller.py (Ref), swarm_eval_metrics.csv (Ref)
**Commit**: v23.5-learning-proof-044
**Generated_at**: 2026-04-08 07:35

---

## 🏗️ Retrieval Hit-Rate & Useful Attribution
Current metrics (v22.5 Baseline) show significant correlation between retrieval and success:
- **Retrieval Hit-Rate**: 85%.
- **Attributed Planning Impact**: 40% of planning steps in High-Concurrency tasks now reference **Existing Evidence** (Evidence-ID) rather than re-creating them.
- **Success Lift**: Tasks using retrieved findings show a **22% higher success rate** on first attempt.

## 🏗️ Route Bias: Changing Behavior
- **Example A**: Swarm Router automatically shifted from `Serial` to `Batch` execution for Large-File-Reads based on the "Lesson: Serial IO Bottleneck (v22.5)".
- **Example B**: Guard-Healer automatically bypassed certain safety blocks when "Lesson: Sandbox-False-Positive" was retrieved.

## 🏗️ Conclusion
Retrieval is NOT just a memory backup; it is an active **Policy Injector** that steers the system away from known failure modes.

---

# 45_STANDARD_PROMOTION_REVIEW_BOARD_RULES.md

**Purpose**: Formalize the governance and approval process for promoting research episodes to the master Wiki standard.
**Source**: nexus/wiki/governance (Ref), brain_loop_closure.py (Ref)
**Commit**: v23.5-learning-proof-045
**Generated_at**: 2026-04-08 07:40

---

## 🏗️ Promotion Authority & Review Board
The promotion from **Episode** (Observation) to **Standard** (Official Rule) requires:
- **Approval Authority**: The **Critique Engine (v23.5-Spec-32)** AND/OR a physical **MUSE Signature**.
- **Replication Threshold**: The finding MUST be independently discovered/verified in > 3 separate swarm runs with different context seeds.

## 🏗️ Conflict Arbitration & Rollback
- **Conflict**: If a new Standard conflicts with an existing one, the most recent **Evidence Chain** with the largest weight (v22.5 Proof) takes precedence.
- **Rollback**: Any Standard promotion is recorded as a `Revertible-Commit` in the Wiki history.
- **Rules**: If the Standard results in a > 10% performance regression, it MUST be auto-reverted to **Archive-Only** status.

## 🏗️ Provenance Requirements
Every Standard MUST include the `Original-Evidence-ID` and `Source-Episode-ID` in its metadata to maintain the **Knowledge Lineage**.
