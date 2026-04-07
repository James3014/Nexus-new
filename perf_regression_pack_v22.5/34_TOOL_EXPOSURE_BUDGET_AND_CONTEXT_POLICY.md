# 34_TOOL_EXPOSURE_BUDGET_AND_CONTEXT_POLICY.md

**Purpose**: Define strict limits on tool exposure and context usage to prevent context drift and rationalization.
**Source**: nexus/router/exposure.py (Ref), tactical_map.json (Ref)
**Commit**: v23.5-alpha-spec-034
**Generated_at**: 2026-04-08 06:51

---

## 🏗️ Exposure Caps
- **Quadrant I (Critical)**: Max 5 Tools.
- **Quadrant II (Operational)**: Max 15 Tools.
- **Quadrant III (Experimental)**: Max 30 Tools.

## 🏗️ Progressive Disclosure
Only disclose tools that match the CURRENT task step. If the task shifts, the Router MUST narrow the toolset dynamically based on the tactical map quadrant.
