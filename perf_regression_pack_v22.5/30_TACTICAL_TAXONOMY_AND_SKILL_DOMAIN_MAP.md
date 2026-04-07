# 30_TACTICAL_TAXONOMY_AND_SKILL_DOMAIN_MAP.md

**Purpose**: Tactical Quadrants and Skill Mapping for Nexus v23.5.
**Source**: tactical_map.json (Schema), Skill Domain Mapping (Ref)
**Commit**: v23.5-alpha-spec-030
**Generated_at**: 2026-04-08 06:38

---

## 🏗️ Tactical Quadrants
- **Q1 (Critical Core)**: Hardened enforcement.
- **Q2 (Operational Support)**: Flexible sync.
- **Q3 (Experimental Research)**: Log-only audit.
- **Q4 (Maintenance)**: Version-locked stable.

---

# 31_DOMAIN_FIREWALL_RUNTIME_CONTRACT.md

**Purpose**: Domain Firewall runtime implementation rules.
**Source**: nexus/router/firewall.py (Ref)
**Commit**: v23.5-alpha-spec-031
**Generated_at**: 2026-04-08 06:39

---

## 🏗️ Enforcement Rules
- **Domain Mismatch**: Return 403 Forbidden.
- **Tool Exposure**: Dynamic filtering based on active domain.

---

# 33_SESSION_DISTILLATION_AND_HANDOFF_PROTOCOL.md

**Purpose**: Token Budgeting and Session Handoff.
**Source**: nexus/services/memory_repository.py (Ref)
**Commit**: v23.5-alpha-spec-033
**Generated_at**: 2026-04-08 06:40

---

## 🏗️ Reset Sequence
- **Trigger**: 85% Token usage.
- **Payload**: Manifest/Lineage/Evidence.

---

# 34_TOOL_EXPOSURE_BUDGET_AND_CONTEXT_POLICY.md

**Purpose**: Context Hygiene and Tool Exposure Budget.
**Source**: nexus/router/exposure.py (Ref)
**Commit**: v23.5-alpha-spec-034
**Generated_at**: 2026-04-08 06:41

---

## 🏗️ Exposure Caps
- **Q1**: Max 5 Tools.
- **Q2**: Max 15 Tools.
- **Q3**: Max 30 Tools.

---

# 35_V23_5_ROLLOUT_GATES_AND_BENCHMARKS.md

**Purpose**: Acceptance Criteria for v23.5 Release.
**Source**: benchmarks/performance_baseline.md (Ref)
**Commit**: v23.5-alpha-spec-035
**Generated_at**: 2026-04-08 06:42

---

## ✅ Release Gates
- **Gate A**: 100% Sandbox pass.
- **Gate B**: 0 rationalization incidents.
- **Rollback**: Divergence triggers auto-revert to v22 Stable.
