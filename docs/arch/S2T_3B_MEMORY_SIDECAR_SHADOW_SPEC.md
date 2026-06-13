# S2T 3B Memory Sidecar Shadow Specification (Phase M0)

Status: DRAFT
Mode: **SHADOW ONLY**

## 1. Overview
The S2T 3B Memory Sidecar is a secondary, low-cost model (Qwen2.5-3B) tasked with maintaining task continuity and state indexing. It operates as a "sidecar" to the main Nexus engine, providing shadow checkpoints and failure classification without direct impact on the runtime environment.

## 2. Roles & Responsibilities

### 2.1 Authorized Actions (Shadow Only)
- **Session Checkpoint**: Generating snapshots of current task progress.
- **Progress Summary**: Condensing logs and receipts into human/agent readable summaries.
- **Failure Classification**: Categorizing encountered errors into standard failure families.
- **Action Proposals**: Suggesting next logical steps based on the current state.
- **Do-Not-Repeat List**: Identifying failed paths to prevent infinite loops.
- **Evidence Indexing**: Linking current state to physical test reports and receipts.
- **Resume Handoff Drafts**: Drafting context for session resumption.

### 2.2 Explicit Prohibitions (Fail-Closed Boundary)
- **NO File Modification**: The sidecar cannot write to any source or configuration files.
- **NO Command Execution**: The sidecar cannot execute shell commands or tests directly.
- **NO Claim Approval**: The sidecar cannot approve its own claims or bypass verification gates.
- **NO Verifier Bypass**: All results must be verifiable by deterministic tools (Rust/Pytest).
- **NO Route Override**: The sidecar cannot override the routing decisions made by the primary selector.
- **NO Direct Memory Write**: Learning Matrix and official project ADRs cannot be updated by the sidecar without review.
- **NO Verification-Free Completion**: It cannot mark a task as "Complete" without explicit evidence refs.

## 3. Shadow Boundary
All sidecar artifacts are strictly stored in `.nexus/metrics/shadow/` or designated shadow-only paths. They are never read by the runtime `S2TStrictGate` for active decision-making during the prototype phase.

## 4. Governance
- **`shadow_only=true`**: Must be explicitly set in all metadata.
- **Schema Gated**: All outputs must strictly adhere to the `nexus.s2t_memory_sidecar_checkpoint.v1` schema.
- **Abstain-First**: If input evidence (logs/receipts) is missing or contradictory, the sidecar must set `claim_boundary="unknown"` and provide an `abstain_reason`.
