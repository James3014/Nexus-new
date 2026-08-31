# Open SWE Integration Contract — Activation V1

contract_id: `OPEN_SWE_INTEGRATION_CONTRACT_V1`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Mode:** `BOOTSTRAP_GOVERNANCE`
- **Status:** `ACTIVE_FOR_G10_G15`
- **Owner decision:** `ACTIVATE_OPEN_SWE_DEFAULT`
- **Owner decision date:** `2026-09-01`
- **Base repository:** `James3014/Nexus-new`
- **Base main:** `30b49473578ec2e9d073d05938345d43dfa87594`
- **Base tree:** `0399dd60cf5d62e3e8dfbb69afc3ab5fd390c87a`
- **Evidence home:** GitHub Issue `#673`, terminal marker `OPEN_SWE_EXECUTION_PRODUCTIONIZATION_V1_READY_FOR_ACTIVATION_DECISION`
- **Auto-chain:** `false` after G15
- **Next authority boundary after merge:** `G16_RUNTIME_ACTIVATION_AUTHORIZATION`

## Mission

Prepare and integrate the source-controlled activation profile that makes Open SWE / Deep Agents the preferred External Intelligence execution runtime for both semantic review and bounded diagnosis/repair, while preserving Nexus as the control/governance plane and preserving OpenCLI/OpenCode as immediate rollback controls.

This contract covers source reconciliation, the activation profile Candidate, independent acceptance, and protected merge only. It does not mutate the loaded host config, restart/reload a service, retire OpenCLI/OpenCode, release, deploy, or claim production runtime activation.

## Bootstrap governance rule

During construction, governance intensity scales with claim and consequence, not with activity. Small implementation/debug iterations inside this frozen scope do not require new Task Cards. High-consequence claims and integration still require exact revision evidence, independent acceptance, and protected merge controls.

The five invariants that remain mandatory are:

1. **Authority** — this Owner-approved contract authorizes only the bounded G10-G15 work below.
2. **Scope** — only the allowed files and activation profile semantics below may change.
3. **Revision/diff** — every acceptance or merge claim binds exact base, head, tree, and changed paths.
4. **Minimum evidence** — existing independent tests, rollback/negative controls, exact config inspection, and independent Candidate review must pass.
5. **Integration boundary** — becoming a merged Nexus capability is distinct from loaded-runtime activation, release, deployment, and OpenCLI/OpenCode retirement.

## Allowed scope

Source reconciliation and activation Candidate may change only:

- `tasks/open-swe-execution-productionization-v1/INDEX.md`
- `tasks/open-swe-execution-productionization-v1/OPEN_SWE_INTEGRATION_CONTRACT.md`
- `scripts/ops/configs/external_intelligence_open_swe_activation_v1.json`

Maximum files: `3`.

## Forbidden scope

Do not change under this contract:

- `AGENTS.md`, CapabilityPlanner, route authority, Workforce Admission, or worker eligibility policy;
- Candidate/receipt/lifecycle schema or acceptance semantics;
- Open SWE adapter implementation, fanout/reconciliation implementation, sandbox implementation, or GitHub controller authority;
- the host file `~/.config/nexus-external-intelligence/config.json`;
- LaunchAgent/service state, runtime reload/restart, release/deploy state, or production data;
- OpenCLI/OpenCode removal or retirement.

Any need to change those surfaces is a contract boundary and must stop this contract rather than widening it silently.

## G10 — campaign source reconciliation

TASK-001 through TASK-004 are physically complete by the G1-G9 evidence chain. Their individual cards remain immutable historical compilation snapshots; current completion/frontier truth is reconciled in `INDEX.md` and this Integration Contract rather than rewriting those old cards.

The reconciliation is bookkeeping of already-proven work. It does not retroactively alter Candidate-production history or expand prior task authority.

## G11 — Owner activation decision

Decision: `ACTIVATE_OPEN_SWE_DEFAULT`.

Meaning for this contract: prepare the preferred activation profile. This decision does not itself mutate a loaded runtime.

## G12 — activation configuration contract

The source-controlled operational activation fragment at `scripts/ops/configs/external_intelligence_open_swe_activation_v1.json` is exactly:

```json
{
  "semantic_backend": "open_swe",
  "worker_backend": "open_swe",
  "open_swe_model_provider": "google_genai",
  "open_swe_model": "gemini-3.7-flash"
}
```

The fragment intentionally contains only existing, already-supported configuration keys. It introduces no new schema and no new authority surface. It lives on the existing operations source surface so the repository's exact-base impact gate treats it as an operational change and selects conservative Tier 2 verification instead of leaving a new runtime-config path unmapped.

Rollback remains:

```json
{
  "semantic_backend": "opencli",
  "worker_backend": "opencode"
}
```

The Open SWE provider/model fields may remain present while rolled back; current configuration validation permits them when the Open SWE backends are not selected.

## G13 — activation Candidate acceptance invariants

The Candidate must prove all of the following:

1. the activation fragment is exactly the four existing keys and intended values above;
2. pre-existing independent service tests prove explicit `semantic_backend=open_swe` selects `OpenSWEExternalIntelligenceTransport` and explicit `worker_backend=open_swe` selects `OpenSWEWorkerTransport`;
3. pre-existing independent service tests prove the library/default control arm remains `semantic_backend=opencli` and `worker_backend=opencode`;
4. the rollback fragment therefore remains executable through already-tested existing configuration seams without deleting the Open SWE provider/model values;
5. no production adapter, route, authority, receipt, Candidate, lifecycle, verifier-policy, or test-inventory implementation changes are present;
6. affected Open SWE/External Intelligence tests pass or exact-base debt is explicitly classified rather than hidden;
7. exact-head GitHub static/security/governance gates pass;
8. changed paths are exactly within the allowed scope and there are no deletions relative to the original base.

Candidate-authored tests are intentionally excluded from the final Candidate so exact-base CI compares a stable test inventory and independent pre-existing oracles remain the behavioral authority.

## G14 — independent acceptance

Independent acceptance must inspect the physical Candidate rather than this contract prose. It must bind exact base/head/tree, full changed-path set, activation fragment bytes, independent existing test evidence, rollback control, exact-base classification, and claim ceiling.

Maximum Candidate claim after G14:

`ACTIVATION_PROFILE_ACCEPTED_FOR_PROTECTED_MERGE`

This does not claim loaded-runtime activation.

## G15 — protected merge

Protected merge is allowed only after G14 acceptance, terminal required checks on the exact head, stable current base, no unexpected scope drift, and expected-head/CAS merge.

Maximum claim after G15:

`OPEN_SWE_ACTIVATION_PROFILE_MERGED_RUNTIME_NOT_ACTIVATED`

## Evidence log

- G1-G9 terminal campaign evidence is durably recorded in Issue #673.
- Current bound base for this contract: `30b49473578ec2e9d073d05938345d43dfa87594`, tree `0399dd60cf5d62e3e8dfbb69afc3ab5fd390c87a`.
- TASK-004 post-merge portfolio included real semantic execution, artifact-aware attribution, ambiguous-outcome recovery, affected regression, and preserved OpenCLI/OpenCode control arm.
- G9 recommendation: `ACTIVATE_OPEN_SWE_DEFAULT`.
- The first Candidate-authored profile test was removed after exact-base CI correctly refused to compare a changed test inventory as ordinary baseline debt; existing independent tests remain the oracle.
- The next exact-base run proved the same pre-existing `test_search_context_isolation` failure on base and head with `new_failures=[]`, but still blocked because the new `configs/runtime/...` path was unmapped and therefore set `impact_class=IMPACT_UNKNOWN`. Diagnosis of `pr_impact_gate.py` confirmed that any `IMPACT_UNKNOWN` classification is intentionally blocking even when failure sets match. The profile was moved to `scripts/ops/configs/...`, an existing conservative operations surface, without changing verifier policy.

## Stop conditions

Stop and require a new authority decision if any of these occur before G15:

- main or Candidate drift changes the semantic subject materially;
- activation requires a new config key/schema rather than the existing four-key fragment;
- adapter/fanout/authority code must change;
- verifier policy would have to be weakened or edited to admit this Candidate;
- rollback no longer selects OpenCLI/OpenCode cleanly;
- exact-base evidence reveals a new Candidate-attributable failure;
- protected merge gates cannot bind the exact accepted head.

After G15, stop at `G16_RUNTIME_ACTIVATION_AUTHORIZATION`.
