# 38_MEMORY_INGEST_DEDUP_AND_JUDGE_POLICY.md

**Purpose**: Formalize the eligibility and deduplication logic for findings entering the core memory repository.
**Source**: nexus/research/wisdom_vault.py (Ref), memory_repository.py (Ref)
**Commit**: v23.5-learning-spec-038
**Generated_at**: 2026-04-08 07:05

---

## 1. Ingest Eligibility
Findings MUST meet these criteria to be accepted into Core Memory:
- **Completeness**: MUST have a valid Evidence ID and Episode Lineage.
- **Signal**: MUST provide a clear "Lesson" or "Refinement" (No duplicate of known state).
- **Veracity**: Verified by the Critique Engine (Spec-32) before ingestion.

## 2. Duplicate Detection (The Dedup Engine)
The Ingest Engine performs a **Semantic Distance Check**:
- **Distance < 0.1**: Redundant finding. Auto-discarded (Logged as Dedup hit).
- **Distance 0.1 - 0.3**: Incremental update. Merge with existing finding.
- **Distance > 0.3**: Unique finding. Create new memory entry.

## 3. Confidence & Trust Tier
- **Tier 1 (Certified)**: Findings with 100% manifest and lineage pass.
- **Tier 2 (Provisional)**: Findings from a single episode (Awaiting replication).
- **Tier 3 (Experimental)**: High-drift research (Stored separately for audit).

## 4. Retention & Pruning Rules
- **Pruning**: Redundant or superseded findings are archived to Arweave after 30 days to maintain high-signal density in the vector index.

---

# 39_WIKI_WRITEBACK_AND_STANDARDIZATION_PROTOCOL.md

**Purpose**: Define the engineering path to promote verified research findings into the authoritative Nexus Wiki standard.
**Source**: nexus/wiki/governance (Ref), brain_loop_closure.py (Ref)
**Commit**: v23.5-learning-spec-039
**Generated_at**: 2026-04-08 07:07

---

## 1. Episode to Standard Promotion Path
1. **Discovery**: Research episode identifies a performance or rule improvement.
2. **Replication**: The finding is verified across > 3 independent swarm episodes.
3. **Promotion Trigger**: The Ingest Engine marks the finding as `STANDARD-READY`.
4. **Draft Generation**: Automated drafting of the new Wiki section based on Evidence.

## 2. Required Evidence for Writeback
- **Lineage ID**: 100% trace to the source research.
- **Impact Delta**: Verified performance improvement (e.g., < 30ms latency increase).
- **Approval Signature**: Automated sign-off from the **Critique Engine (v23.5-Spec-32)**.

## 3. Conflict Handling
If a new finding conflicts with an existing Wiki standard:
- **Conflict Flag**: Immediate HUD alert.
- **Decision**: The most recent evidence takes precedence ONLY if it has a higher **Trust Tier** (Spec-38).
- **Provenance**: Preserve the "Old Standard" as a historical reference in the evidence chain.

## 4. Rollback Protocol
- Every writeback event triggers a `git commit` with the `writeback` tag.
- Reverting to a previous Wiki state MUST be possible via a single `nexus restore --wiki-state=<timestamp>` command.
