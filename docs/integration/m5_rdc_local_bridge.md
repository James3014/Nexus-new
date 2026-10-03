# M5 RDC Local Assist and Qualified Local Worker Bridge

**Authoritative Issue**: [James3014/Nexus-new#1336](https://github.com/James3014/Nexus-new/issues/1336)
**Execution Authority / Transport**: Direct Delegated / RDC (`transport_kind = RDC`, `host = M5`, `service_mode = LOCAL` under [#1266](https://github.com/James3014/Nexus-new/issues/1266))
**Claim Ceiling**: `LOCAL_NON_AUTHORITATIVE_EVIDENCE_ONLY`
**Host Target**: Apple M5 Pro (64 GB Unified Memory)
**Dispatch Plane**: RDC (Remote Desktop Commander)

---

## 1. Architectural Overview & Owner Intent

The M5 Local Integration operationalizes local compute resources (Apple Silicon M5 Pro) directly accessible from Main GPT coordination via **RDC (Remote Desktop Commander)**.

### Target Dispatch Architecture

```text
                         Main GPT
                            |
                  Coordination / evidence
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
   GPT Direct          RDC Online           RDC Local
    Dev MCP              Worker               Worker
        |                   |                   |
      repo             Gemini/Codex/...      M5 runtime
                                                |
                                        llama.cpp / MLX /
                                        qualified runtime
```

### Critical Architectural Invariants

1. **RDC is the External & Local Dispatch Transport**:
   - Dev MCP is strictly retained for direct Main GPT interactive operations and bounded Core/Candidate recovery.
   - Dev MCP is **not** used as a dispatch plane for local or external workers.
   - Local execution runs via existing authorized lanes (`DIRECT_DELEGATED` with `transport_kind = RDC`, `host = M5`, `service_mode = LOCAL` per [#1266](https://github.com/James3014/Nexus-new/issues/1266)). No redundant `LOCAL` authority lane is introduced.
2. **Two Operational Modes**:
   - **Mode A (Local Assist)**: Read-only repository localization and candidate ranking. Strict invariant: `LOCAL_ASSIST_MUTATION_AUTHORITY = False`.
   - **Mode B (Local Worker)**: Bounded substrate execution only (read-only / non-mutating text generation). Mutation invariant: `LOCAL_WRITE = DENY_UNQUALIFIED`. Local coding worker is **not** qualified for repository mutation; `write_performed` remains `False`.
3. **No Redundant Authorities**:
   - Reuses [#1266](https://github.com/James3014/Nexus-new/issues/1266) for live execution provenance.
   - Handoff packets are strictly ephemeral inputs (`durability = EPHEMERAL_PROJECTION`, `nature = HANDOFF_INPUT`) consumed by the external coordinator / `nexus-runtime#45`. No secondary durable coordination store or claim authority is created.
   - External prerequisites [#129](https://github.com/James3014/Nexus-new/issues/129) (work claims/fencing) and [#98](https://github.com/James3014/Nexus-new/issues/98) (cross-entrypoint physical mutation domain conflict) are coordinated externally; this bridge does not mint or self-validate them.
4. **Independent RIE Ownership**:
   - Deterministic candidate localization is performed via `nexus/services/m5_local/deterministic_fallback.py` (`nexus.m5_local.deterministic_fallback_packet.v1`). It does not reimplement or claim equivalence to canonical RIE.

---

## 2. Modes of Operation

### Mode A: Local Assist (Read-Only)

Mode A enables Main GPT or RDC workers to offload repository intelligence, candidate ranking, and diagnostic queries to local models without risking repository state.

- **Authority Boundary**: Read-only repository introspection.
- **Evidence Linking**: Claims and candidate rankings are deterministically bound to file paths, line ranges, and SHA revisions via deterministic excerpt indexing.
- **Safety Enforcement**: Any attempt to write or touch repository files during an assist call immediately aborts with `LocalAssistMutationAttemptedError`.
- **Deterministic Fallback**: If local model inference is disabled, unavailable, or encounters resource limits, Mode A falls back cleanly to deterministic candidate path ranking and source excerpts.

### Mode B: Local Worker (Bounded Execution Substrate)

Mode B provides an isolated execution substrate for bounded non-mutating tasks.

- **Default State**: `DENY_UNQUALIFIED`.
- **Mutation Boundary**: Physical mutation remains strictly disabled (`LOCAL_WRITE = DENY_UNQUALIFIED`, `write_performed = False`). Any request with `write_permitted = True` fails closed immediately with `LOCAL_ROLE_NOT_QUALIFIED`.
- **Read-Only Substrate**: Supports bounded execution of inspection or generation tasks returning textual output without modifying workspace files.

---

## 3. Predecessor-Successor Handoff Input Projection

When local operations hit boundaries (context limit, model capability shortfall, resource pressure, or timeout), execution is not dropped. Instead, an ephemeral **Handoff Packet** is constructed as an input projection for the external coordinator / `nexus-runtime#45`:

```json
{
  "schema": "nexus.m5_local.handoff_input.v1",
  "task_id": "task-xyz",
  "work_id": "work-123",
  "predecessor_attempt_id": "att-local-1",
  "predecessor_operation_id": "op-local-1",
  "repo_identity": "James3014/Nexus-new",
  "base_sha": "5f201a6cb9f7fb7e951642aee3907fec3fd8f39d",
  "inspected_paths": ["nexus/services/live_execution_provenance.py"],
  "evidence_refs": ["path:nexus/services/live_execution_provenance.py"],
  "diff": "",
  "unresolved_question": "Requires online architectural synthesis under #98",
  "escalation_reason": "LOCAL_RESULT_INSUFFICIENT",
  "durability": "EPHEMERAL_PROJECTION",
  "nature": "HANDOFF_INPUT"
}
```

The handoff packet includes a deterministic SHA-256 integrity hash (`handoff_hash()`), ensuring transparent succession by Online workers without loss of local findings or re-running expensive indexing.

---

## 4. Host Qualification & Resource Safety

### Hardware & Runtime Discovery (`nexus/services/m5_local/host_inventory.py`)

The bridge automatically discovers and classifies local assets truthfully:
- **Host**: Apple M5 Pro, 64 GB unified memory (platform-aware: returns explicit `0` RAM and `UNKNOWN` on non-Darwin CI).
- **Runtimes**:
  - `llama.cpp` (`/opt/homebrew/bin/llama-cli`, version 0.4.1, build 10964)
  - `MLX` (`/Users/james/.omlx/bin/omlx-cluster-python`, versions `mlx 0.32.2`, `mlx_lm 0.32.0`; runtime environment available and import-ready, but model inference is not bound on host)
- **Discovered GGUF Models**:
  - `qwen36-35b-q4` (`Qwen3.6-35B-A3B-Q4_K_M.gguf`, ~20.4 GB)
  - `occamy-1.0-q4` (`occamy-1.0-Q4_K_M.gguf`, ~21.2 GB)
  - `occamy-1.0-q8` (`occamy-1.0-Q8_0.gguf`, ~36.9 GB)
  - `occamy-1.0-fit-q5` (`occamy-1.0-abliterated-FIT-REFERENCE-24G-Q5_K_M.gguf`, ~25.3 GB)

### Truthful Role Qualification

Physical file presence is **not** functional qualification:
- Without physical Nexus Learning qualification receipts, all models have all functional roles (`ROLE_REPO_RANKING`, `ROLE_TYPED_DECISION`, `ROLE_READ_ONLY_ASSIST`, `ROLE_BOUNDED_CODE_PATCH`) set to `NOT_QUALIFIED`.
- Physical model execution is separated from role qualification: runtime can execute models, but role eligibility remains `NOT_QUALIFIED` until formal receipt verification.
- Model identity attestation binds observed model to physical file name, exact byte size, execution command, and runtime version.

### Memory & Swap Policy (`nexus/services/m5_local/telemetry.py`)

To protect the host from swap thrashing or memory lockouts:
- **Max Safe Swap**: 16 GB (`MAX_SAFE_SWAP_USED_MB = 16384.0`).
- **Min Free Pages**: 5,000 pages (~80 MB immediate free pages).
- Platform-aware fail-closed: Non-Darwin platforms or inspection failures return `RESOURCE_STATE_UNAVAILABLE`.
- If thresholds are exceeded, local inference requests are refused early with typed escalation `LOCAL_RESOURCE_PRESSURE`.

---

## 5. CLI & Operator Usage

The bridge provides a standalone CLI interface (`nexus/services/m5_local/cli.py`).

### 1. Inspect Host Inventory
Inspect hardware, memory, available runtimes, and model qualification states:
```bash
python -m nexus.services.m5_local.cli inspect
```

### 2. Check Execution Safety Status
Check real-time memory and swap availability:
```bash
python -m nexus.services.m5_local.cli status
```

### 3. Mode A Local Assist
Run a read-only repository query:
```bash
python -m nexus.services.m5_local.cli assist \
  --task-id "task-001" \
  --query "live execution provenance cross entrypoint conflict" \
  --repo-path "/Users/james/workspace/Nexus-new" \
  --base-sha "5f201a6cb9f7fb7e951642aee3907fec3fd8f39d" \
  --model "qwen36-35b-q4" \
  --runtime "llama.cpp"
```

### 4. Mode B Local Worker
Run a bounded worker invocation:
```bash
python -m nexus.services.m5_local.cli run \
  --task-id "task-002" \
  --instruction "Inspect test coverage in isolated worktree" \
  --repo-path "/Users/james/workspace/Nexus-new" \
  --base-sha "5f201a6cb9f7fb7e951642aee3907fec3fd8f39d" \
  --model "qwen36-35b-q4" \
  --runtime "llama.cpp"
```

---

## 6. Verification & Negative Matrix

The test suite enforces a comprehensive negative matrix covering 20 failure and containment modes (`tests/services/m5_local/test_negative_matrix.py`):
1. Runtime not installed -> `LOCAL_RUNTIME_UNAVAILABLE`
2. Model file missing -> `LOCAL_RUNTIME_UNAVAILABLE`
3. Requested vs observed model mismatch -> `LOCAL_MODEL_IDENTITY_MISMATCH`
4. Malformed model output -> `LOCAL_RESULT_INSUFFICIENT`
5. Process timeout -> `LOCAL_TIMEOUT`
6. Cancellation -> `CANCELLED`
7. Non-zero exit code -> clean escalation
8. Output truncation -> bounded containment
9. Memory resource pressure -> `LOCAL_RESOURCE_PRESSURE`
10. Stale repository base SHA -> `StaleBaseError` (fail-closed)
11. Source evidence unavailable -> explicit empty candidate handling
12. Mode A attempted write -> `LocalAssistMutationAttemptedError`
13. Mode B unqualified write -> `LOCAL_ROLE_NOT_QUALIFIED`
14. Handoff missing required predecessor evidence -> `HandoffContractError`
15. Unknown effect -> fail closed
16. Confidence is not completion -> strictly non-authoritative
17. Missing source reference notices -> explicit indication
18. Local failure never triggers rogue auto-dispatch
19. Lineage preserved across local-to-online escalation
20. Cache deletion resilience -> stateless reconstruction from git
