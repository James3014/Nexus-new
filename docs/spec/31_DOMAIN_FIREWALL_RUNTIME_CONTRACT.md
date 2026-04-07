# 31_DOMAIN_FIREWALL_RUNTIME_CONTRACT.md

**Purpose**: Formalize the Domain Firewall behavior within the Nexus Router to prevent cross-domain tool misuse and manage runtime security boundaries.
**Source**: nexus/router/firewall.py (Ref), tactical_map.json (Schema)
**Commit**: v23.5-alpha-spec-031
**Generated_at**: 2026-04-08 01:05 (System Local)

---

## 1. Current Domain Contract
Every agent session MUST be initialized within a specific **`current_domain`** (e.g., Q1, Q2, Q3, Q4). This domain acts as the "sandbox" for all tool calls.

## 2. Undeclared-Domain Behavior
- **Strict Enforcement**: If a tool is called from a domain not explicitly declared for that tool in `tactical_map.json`, the Router MUST block the call.
- **Default Action**: Return `403 Forbidden: Domain Mismatch`.

## 3. Tool Exposure Policy
Exposure is filtered by the session's active domain. 
- **Filter logic**: `ToolList = [T for T in AllTools if CurrentDomain in T.AllowedDomains]`.

## 4. Domain Escalation & Switching Rules
- **Promotion**: Require **Evidence-based Request** (EBR). The Critique Engine must pre-scan the intent before allowing a domain shift (e.g., Q2 -> Q1).
- **Demotion**: Automatic on task completion to prevent "privilege drift".

## 5. Failure / Fallback Behavior
- **Failure**: On 403, the session is PAUSED.
- **Fallback**: Auto-narrow the context and re-request intent clarification via the HUD.

## 6. Observability Requirements
- **Logs**: Every "access denied" event MUST be recorded as a `FirewallViolation` event in the trace logs for audit-retrieval.

---

# 32_CRITIQUE_ENGINE_POLICY_AND_ANTI_RATIONALIZATION.md

**Purpose**: Formalize the Critique Engine's role in detecting and preventing "rationalization loops" where the agent justifies unsafe or out-of-scope actions.
**Source**: nexus/policy/critique.py (Ref), research/evidence_integrity.md (Ref)
**Commit**: v23.5-alpha-spec-032
**Generated_at**: 2026-04-08 01:07 (System Local)

---

## 1. Intent Pre-scan Flow
Before executing ANY high-impact tool (Q1/Q2), the Critique Engine MUST perform a pre-scan:
1. **Analyze Input Description**.
2. **Predict Impact Scope**.
3. **Compare against "Banned Patterns"**.

## 2. Anti-Rationalization Rules
- **Definition**: Rationalization is defined as an explanation that uses "convenience" or "system limitation" to bypass safety/domain rules.
- **Rule CR-01**: Explanations starting with "I need to do this because..." that lead to a Q1 violation will trigger an immediate **Halt-and-Verify**.

## 3. False Positive Handling
- If the Critique Engine blocks a valid action, it MUST provide a **"Path to Approval"** (e.g., provide specific Evidence X to continue).

## 4. Human Override Path
- For emergency operations, a **MUSE-Level Override** (Physical token or confirmed CLI prompt) can bypass Critique blocks, but this event is pinned as a P0 audit event.

## 5. HUD / Warning Behavior
- **HUD Color-coding**:
  - Yellow: Suspicious Pattern detected (Soft warning).
  - Red: Policy Violation (Hard block/HUD HUD flash).

## 6. Evidence Logging Requirements
The critique logic used to block an action MUST be serialized into the session metadata as part of the **Evidence Chain**.
