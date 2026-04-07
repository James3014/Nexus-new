# 37_BRAIN_LOOP_AUTOMATION_AND_TRIGGER_SPEC.md

**Purpose**: Automated execution triggers for the brain_loop_closure engine.
**Source**: scripts/ops/brain_loop_closure.py (Ref)
**Commit**: v23.5-alpha-spec-037
**Generated_at**: 2026-04-08 07:20

---

## 🏗️ Trigger Points
1. **Task Success (Exit 0)**: Ingest findings.
2. **Swarm Batch End**: Cross-episode synthesis.

## 🏗️ Post-Run Hook
`swarm_harness.py` will execute `brain_loop_closure.py --mode=async` as a child process.
