# RIE knowledge applicability as codeintel evidence: G0 source inventory (#1579)

Status: G0 inventory frozen against `origin/main` 36c802ec8. Scope: Nexus-new only.
Producer: Repository Intelligence Engine `88285acf570688befbc8e36eb73f46987171bd4e`
(`knowledge` CLI operation, schema `reviewer.knowledge_applicability.v1`).

Exact next gate named by the Issue: `RIE_KNOWLEDGE_CODEINTEL_G0_SOURCE_INVENTORY_FREEZE`.

## What the producer requires

`analyze_knowledge_applicability` takes: `snapshot` (repository, pr_number, head_sha,
base_sha, current_main_sha), `knowledge_artifacts[]` (`artifact_id`, `path`,
`source_refs[]` of `{source_path, expected_content_sha256}`, `covers[]` globs),
`changes[]` (`kind` ADD/MODIFY/DELETE/RENAME, `path`, `old_path`),
`observed_source_sha256`, `in_scope`, `collection_complete`, `collection_errors`.

## Inventory (from current Nexus-new source)

| Input | Source today | Verdict |
| --- | --- | --- |
| Repo / revision identity | Planner/Task/PR context already carries repository, head/base/main SHAs (GitHub orchestration contracts, `repository_contract_gate`). `pr_number` is a RIE requirement; a non-PR codeintel task has none. | PARTIAL. Available only when the caller has a PR-bound identity. Otherwise the adapter reports `REVISION_IDENTITY_UNAVAILABLE`. |
| Repository-owned knowledge artifacts with `source_refs` + `expected_content_sha256` | None. `nexus_wiki_vault` pages (`99_Schema/generated/agent-index.json`) carry only `content_sha256` of the page itself and `content_verified_against_commit` (a commit, not per-source hashes). Page front matter has `raw_sources:` (free-form, empty in most of 13 occurrences), no hashes. `openwiki/`, `docs/`, `nexus/knowledge/` have no `source_refs`/`covers`. Other `source_refs` hits (`nexus/research/learn/ingest_service.py`, `nexus/learning/skill_fit_followup.py`) are research-claim bookkeeping, not repository knowledge freshness. | NOT AVAILABLE. No authoritative artifact expresses a source relation. |
| Declared `covers` | None in any repo-owned artifact (`^covers:` grep over wiki, openwiki, docs is empty). | NOT AVAILABLE. |
| Changed-path evidence | `git diff --name-status` is already used in `nexus/orchestrator/repository_contract_gate.py` and `self_hosted_task_service.py`; no shared normalized helper to RIE `changes[]` (the gate also rejects renames). | AVAILABLE as raw git evidence; a normalizer is not built here. |
| Observed source hashes | Computable from git blobs / working tree; no existing canonical per-path hash collector for codeintel. | AVAILABLE in principle; not built here. |
| In-scope boundary | Not declared by any current artifact. | NOT AVAILABLE; must be owner-declared with the knowledge artifacts. |

## Decision

No current authoritative knowledge artifact can express a source relation. Per the Issue,
this change does NOT invent a global knowledge store and does NOT synthesize claims in
runtime. G1/G2 are therefore scoped to an adapter that:

* takes already-normalized knowledge-claim inputs from a caller;
* fails closed when they are absent, yielding explicit `NOT_APPLICABLE` evidence
  (`KNOWLEDGE_CLAIM_SOURCE_NOT_AVAILABLE`), never `CURRENT`;
* invokes the pinned engine only by subprocess (`NEXUS_RIE_ENGINE_ROOT`,
  `NEXUS_RIE_PYTHON_BIN`, default `python3`), after `git rev-parse HEAD` equals the pinned
  revision (`RIE_ENGINE_REVISION_MISMATCH` otherwise);
* verifies schema, content hash, claim ceiling and exact revision identity.

Runtime wiring of a live claim source (G3) stays blocked on a bounded follow-up that
defines a repo-owned knowledge manifest (artifact id/path, `source_refs` with hashes,
`covers`, in-scope), owned by whoever owns that knowledge, plus normalizers for changes and
observed hashes.

## G2 projection contract

Fields under `knowledge_applicability` in the existing codeintel `consumer_payload`
(`nexus.consumer_payload.v1`), bounded by the existing 2000-char cap:
`schema`, `status` (`COMPLETE`/`INCOMPLETE`/`NOT_APPLICABLE`), `relation_counts`
(`CURRENT`, `STALE_EXACT_SOURCE`, `AFFECTED_BY_COVERAGE`, `UNKNOWN`),
`affected_artifact_refs` (max 4), `uncovered_change_refs` (max 4), `evidence_gaps` (max 4),
`report_hash`, `report_schema`, `rie_claim_ceiling`, and
`claim_ceiling = PLANNER_SELECTED_CODEINTEL_KNOWLEDGE_APPLICABILITY_CONTEXT_ONLY`.
Reason codes and document/source text are never forwarded. An affected artifact means
review-needed, not semantically wrong. CapabilityPlanner remains the sole selector and
#472 package identity / consumer receipts remain the consumption authority.
