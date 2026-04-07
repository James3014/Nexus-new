# 30_TACTICAL_TAXONOMY_AND_SKILL_DOMAIN_MAP.md

## 1. Tactical Quadrants (The Domains)
Nexus v23.5 classifies all available skills and agent actions into **Four Tactical Quadrants (Q1-Q4)**:

| Quadrant | Name | Enforcement Level | Default Behavior |
| :--- | :--- | :--- | :--- |
| **Q1** | **Critical Core** | **MAX (Hardened)** | Block-on-Drift / Atomic Sync Required. |
| **Q2** | **Operational Support** | **MED (Flexible)** | Warn-on-Drift / Batch Sync allowed. |
| **Q3** | **Experimental Research** | **LOW (Observational)** | Log-only / Sandboxed execution. |
| **Q4** | **Maintenance/Legacy** | **STABLE (Guarded)** | Strict Version Lock / No auto-updates. |

## 2. Skill-to-Domain Mapping Schema
For each Skill (MCP or Python Tool), it MUST map to at least one Tactical Domain:
- **`skill_id`**: Unique identifier.
- **`primary_domain`**: The Q-level.
- **`enforcement_mode`**: `Strict` | `Lax` | `Audit`.
- **`impact_weight`**: 0.0 - 1.0 (Higher values require more Evidence).

## 3. Conflict Resolution Rules
If a Skill is mapped to multiple domains:
- **Safety First**: The most restrictive domain (Q1 > Q4 > Q2 > Q3) takes precedence.
- **Logic Override**: If the Brain (Logic) provides Evidence for a domain promotion, its classification overrides the default.

## 4. Default Domain Behavior (Unknown Skills)
- **New Skills**: Automatically assigned to **Q3 (Experimental)** for the first 100 sessions.
- **Legacy Tools**: Default to **Q4 (Maintenance)** until re-certified for v23.5.

## 5. Tactical Map Versioning
The `tactical_map.json` file will follow semantic versioning. Major version increments (v1 -> v2) require a **Full System Integrity Re-check (FSR)**.

> [!TIP]
> **"Evidence-First"**: Mapping is NOT static. It is a live reflection of **Fusion Efficiency**.
