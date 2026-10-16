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

## G0 follow-up: manifest (#1579)

Claim ceiling for this step: `REPOSITORY_KNOWLEDGE_MANIFEST_DECLARATION_ONLY`.

The G0 inventory above found no repo-owned artifact that declares source relations.
This follow-up adds the smallest owner-reviewable one:
`docs/knowledge/rie_knowledge_manifest.v1.json` (schema
`nexus.rie_knowledge_manifest.v1`). It is **owner-declared, not derived**: nothing infers
a relation from document text, and nothing in runtime writes to it.

### Manifest contract

Top level: `schema`, `revision` (the commit at which every `expected_content_sha256` was
computed), `claim_ceiling`, `notes`, `entries[]`. Each entry:

| Field | Meaning |
| --- | --- |
| `id` | Unique stable artifact id (becomes RIE `artifact_id`). |
| `path` | Repo-relative knowledge artifact (a doc intended as model context). |
| `source_refs[]` | `{path, expected_content_sha256}`: sources the doc explicitly names; sha256 is over the git blob bytes at `revision`. |
| `covers[]` | Narrow globs of additional paths whose change should flag the doc for review. A bare `*`/`**` is rejected. |
| `in_scope` | Must be `true`; the union of covers and source paths is the RIE `in_scope` boundary. |

Declared today (each doc literally names the source files it describes):

* `rie-guard-semantic-delta-g0`: `docs/integration/rie_guard_semantic_delta_g0.md` ->
  `scripts/ops/canonical_owner_guard.py`, `scripts/ops/rie_guard_delta_evidence.py`.
* `rie-knowledge-applicability-codeintel-g0`: this document ->
  `nexus/services/rie_knowledge_applicability.py`.
* `m5-rdc-local-bridge`: `docs/integration/m5_rdc_local_bridge.md` ->
  `nexus/services/m5_local/{deterministic_fallback,host_inventory,telemetry,cli}.py`.

`docs/architecture/AI_CONTROL_PLANE_BOUNDARY.md` was considered and **not** declared: it
names no source file, so any relation would be invented.

### How to extend

Add an entry only when the document explicitly names the files it describes and is genuinely
model context. Compute each hash with `hashlib.sha256` over the blob bytes at the new
`revision` (`git show <revision>:<path>`), bump `revision` for the whole manifest, and keep
`covers` narrow. Re-hashing sources after a source change is an owner act: it asserts the
doc was reviewed against the new source.

### STALE_DECLARATION is surfaced, never hidden

`nexus/services/rie_knowledge_manifest.py` validates the schema (fail closed on a malformed
manifest) and recomputes source hashes. A source whose current hash differs from the
declared one, or is missing, marks that entry `STALE_DECLARATION` per entry; loading does not
fail. The producer forwards those as `MANIFEST_STALE_DECLARATION:<id>` entries in the
projection's `evidence_gaps` and in the artifact's `manifest` block, and the pinned RIE engine
independently reports the relation as `STALE_EXACT_SOURCE` (review needed, not "wrong"). An
entry whose artifact file is missing at head is excluded from the claims and reported as a
declaration gap, never as `CURRENT`.

### Producer wiring (no runtime selection)

`build_manifest_knowledge_evidence` (same module) takes repo root, PR identity
(repository, pr_number, head/base/current_main sha), the manifest and
`git diff --name-status base..head` output, builds `changes[]` (ADD/MODIFY/DELETE/RENAME) and
`observed_source_sha256` (git blobs at head), and calls the existing
`build_codeintel_knowledge_evidence`. `scripts/ops/rie_knowledge_evidence.py` is the CLI
(`NEXUS_RIE_ENGINE_ROOT`, `NEXUS_RIE_PYTHON_BIN`; `--output`, `--step-summary`). It exits 0
with an explicit `NOT_APPLICABLE` artifact when the engine is unconfigured, exits 0 with
`ADVISORY_INCOMPLETE` on adapter/engine failures, and exits 1 on malformed identity. No model
call. Because `covers` and source paths define `in_scope`, `uncovered_change_refs` is
structurally empty for this manifest; it reports only declared relations.

### G3 wiring (done) and what proof remains

Wired: `nexus/services/rie_knowledge_codeintel_hook.py::knowledge_applicability_evidence`
is called from the `codeintel` invoker in `build_default_mainchain_invokers` (both the
real-executor branch and the preflight-only branch) and merges `knowledge_applicability`
into the invoker `evidence`; the pinned runtime extractor then places it in the codeintel
`consumer_payload` of the #472 bundle. The invoker only runs when CapabilityPlanner selected
`codeintel`; no Planner capability, route, approval or merge authority was added.

Identity: RIE is PR-centric, so the caller may supply an optional request field
`rie_knowledge_identity` = `{repository, pr_number, base_sha, current_main_sha}`
(`current_main_sha` defaults to `base_sha`). It is forwarded only by the
`capability_context` construction in
`SelfHostedTaskService._worker_context_materialization` and validated by the hook
(`owner/repo`, positive int, 40-hex SHAs). `head_sha` is the lease `target_revision` and must
equal `git rev-parse HEAD` of the target worktree. The manifest is read from that worktree.

Fail-closed behaviour (sub-evidence only, the codeintel stage is never changed or crashed):
no/invalid hint, unusable revision, engine not configured (`RIE_ENGINE_ROOT_NOT_CONFIGURED`)
or HEAD mismatch (`HEAD_REVISION_MISMATCH`) -> `NOT_APPLICABLE`; engine, report or manifest
integrity failure -> `INCOMPLETE` with gap `RIE_KNOWLEDGE_REJECTED:<code>`. Never `CURRENT`
without a verified report.

Proof in tests: stubbed-engine seam test through the real #472 materialization and worker
consumption receipt (`tests/nexus/orchestrator/test_worker_planner_context_input.py`), plus an
opt-in real-engine test (`NEXUS_RIE_ENGINE_ROOT` set) in
`tests/services/test_rie_knowledge_codeintel_hook.py`.

Still open (G3): one live Gateway run of a real Planner-selected `codeintel` task that carries
`rie_knowledge_identity`, with `NEXUS_RIE_ENGINE_ROOT` configured on the host, showing the
verified RIE report hash inside the serialized package and the WorkerRegistry physical
provider-input receipt, plus an independent verifier.
