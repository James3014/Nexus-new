# Local Model Armor: Four-Path Reality Audit (P1)

## 1. Verified Audit Conclusions

The execution status and division of responsibilities across the four paths are verified as correct:
- **Path A**: Owns the absolute routing truth source.
- **Path B**: Controls the local model execution capability pipeline.
- **Path C**: Validates fail-closed bridge/contract semantics.
- **Path D**: Classified strictly as diagnostic-only.

---

## 2. Codebase Facts and Audit Anchors

The codebase state has been validated with the following facts:
- `scripts/bench/capability_ab_runner.py` is the Path A mainline runner.
- `nexus/services/local_heal/capability_planner.py` acts as the route planner.
- `nexus/services/local_heal/capability_adapter.py` acts as the B/C adapter seam.
- `nexus/contracts/hybrid_route.py` exists and is the contract checking fail-closed route decisions.
- **Current Seam State**: `capability_ab_runner.py` currently has zero imports or references to `LocalHealCapabilityAdapter` or `capability_adapter` modules.

---

## 3. Required Implementation Corrections

Based on the audit, the following adjustments are recorded:
- **P4 is implementation, not confirmation**: Direct runner-to-adapter wiring must be implemented as new code in P4.
- **P2 is simplified**: `hybrid_route.py` already guards the majority of security invariants, requiring only minor test coverage hardening.
- **P3 must define adapter-to-runner row mapping schema**: A clear schema mapping rule must be documented prior to wiring.
- **P1 is DONE**: This document serves as the official archival artifact, marking P1 complete.

---

## 4. Status Table

| Path | Status | Main File | Integration State |
|---|---|---|---|
| A | verified mainline | `scripts/bench/capability_ab_runner.py` | route truth |
| B | exists | `nexus/services/local_heal/*` | local pipeline |
| C | exists | `nexus/contracts/hybrid_route.py` & `capability_adapter.py` | bridge scaffold |
| D | exists | `scripts/local_heal/*` | diagnostic only |

---
**Audit Status**: DONE
