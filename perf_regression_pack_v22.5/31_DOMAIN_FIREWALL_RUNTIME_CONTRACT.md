# 31_DOMAIN_FIREWALL_RUNTIME_CONTRACT.md

**Purpose**: Formalize the Domain Firewall behavior within the Nexus Router to prevent cross-domain tool misuse.
**Source**: nexus/router/firewall.py (Ref), tactical_map.json (Ref)
**Commit**: v23.5-alpha-spec-031
**Generated_at**: 2026-04-08 06:45

---

## 🏗️ Enforcement Protocol
1. **Domain Mismatch**: If a tool is called from a domain not explicitly declared in `tactical_map.json` for the current session, the Router MUST block the call.
2. **Response Code**: Return `403 Forbidden: Domain Mismatch`.
3. **Escalation Path**: Require Evidence-based Intent (EBI) to promote a session quadrant (e.g., Q2 -> Q1).

---
## ✅ Runtime Invariants
- `ActiveDomain` MUST be set at session initialization.
- `ToolExposure` MUST be filtered by `CurrentDomain` status.
