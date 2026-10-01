# Issue #330 — full Tier 3 inventory and disposition

## Scope and terminal boundary

Owner requested Wave 1 (#406 candidate/draft PR) and Wave 2 (#330 full-regression diagnosis). This directory completes the Wave 2 inventory and evidence-bounded first-failure disposition. It does not repair production code/tests, make every ultimate root cause proven, authorize Wave 3, merge a PR, deploy a runtime, or claim repository-wide green. `AUTO_CHAIN=false`; #330 remains open.

The prior 320 `CAUSAL_ADJUDICATION_REQUIRED` records have been examined against exact source and full-run traces and resolved into 101 bounded diagnostic groups. Three non-hermetic test nodes retain explicit original-trigger unknowns; their test/environment classification is supported, but the original readiness subcheck or CLI exception was not preserved by the full-run tests. See `residual_causal_questions` before any repair. Isolated success alone is not permission to change production behavior.

## Exact full-run evidence

Historical run `31925711602`, job `95112840837`, source `52927467b1404e71058b6aef4fed8f4e8f51c62a`: 746 failed, 5 errors, 13,126 passed, 36 skipped. Original JUnit artifact `9257930120` returns 404. The exact original job log was recovered instead; it is not fabricated XML. Log SHA-256: `96ef0ef63725d9cce3a58a9bb25b012b3c79e93d129d339ade3a645adba0b940`.

Fresh manual full-regression run `36837565415`, job `110288592865`, source `199feb12fdd9726684785d5420e6b48da03a155f`:

- 18,212 passed, 462 failed, 5 errors, 37 skipped, 1 deselected.
- 18,716 JUnit cases; artifact `11151528361`.
- Command: `uv run pytest tests/ -v --timeout=300 --junitxml="$RUNNER_TEMP/full-regression.xml"`.
- GitHub Actions Python 3.12 full-regression realm, `NEXUS_TEST_MODE=CI`; not a PR impact-only run.
- JUnit SHA-256: `11ffa9063750b544db847a93eeedbbe5a8e38cd9c7d03697ac8b63bd2662400b`.
- ZIP SHA-256: `063cf67dfe9a3514891f5e9efb692744c6d14dcf6b2e659c3705f208eafcb302`.

All 751 historical failed/error node IDs map into the current JUnit: 373 now pass, 373 still fail, 5 still error. Another 89 failures are newly observed, not automatically newly introduced regressions. The union contains exactly 840 unique nodes.

## Final disposition and evidence strength

| Disposition | Nodes |
| --- | ---: |
| ALREADY_FIXED at the full-run revision | 373 |
| TEST_OR_ENV_DEFECT | 353 |
| CURRENT_DEFECT — bounded source/consumer/contract mechanism | 100 |
| EXISTING_ISSUE_OWNS_IT | 14 |
| Unclassified first-failure dispositions | 0 |

These are test-node counts, not 100 independent production bugs or 353 harmless tests. The 467 current nonpass nodes are covered exactly once by 119 bounded follow-up packets. Existing owners and already-created follow-up issues are preserved; no packet grants write, provider, acceptance or merge authority.

Current nonpass evidence strength: 14 `PROVEN_OWNER`, 82 retained `SOURCE_CAUSE_PROVEN`, 53 retained `ENVIRONMENT_CAUSE_PROVEN`, 11 `CONTROLLED_CAUSE_SUPPORTED`, and 307 `SOURCE_AND_TRACE_SUPPORTED`. Source-and-trace support establishes the observed first boundary, not every downstream assertion or a production policy change. `all_causal_roots_proven=false` is intentional.

Examples of falsification and narrow readback:

- The 11 pipeline failures reproduce with `NEXUS_LOCAL_QWEN_BACKEND=1`, which bypasses the injected patch client; the same nodes pass with it cleared. Separate committee/protocol-mode controls did not reproduce this family. The earliest writer of the ambient flag is not established. Command identities: `wave2-pipeline-protocol-isolated-control-j4`, `wave2-order-canary-and-exact-wiki-j5`, `wave2-anchored-mode-controlled-canary-j6`, `wave2-qwen-bypass-first-block-controlled-k1`.
- Four recovery/salvage tests pass in isolation, whereas the full-run trace stops at contract/lease identity mismatch. Their canonical rehydration and fixture identity must be rebound before changing recovery logic: `wave2-five-closeout-boundary-k5`.
- HTTP consumers independently reproduced `uv.lock digest mismatch` before the injected OCI runner, proving two additional nodes belong to #1281: `wave2-http-exact-first-exception-k3`.
- Paired local/online harness fails at `workforce_admission_demands_malformed` with zero local calls; this is not evidence that Local assistance reduces effectiveness: `wave2-paired-single-boundary-l3`.
- Owner-finish integration completes but cleanup retains the target on a consumed-approval/execution-contract hash mismatch. Do not remove the cleanup guard; reconcile contract identities first: `wave2-last-four-precise-contract-l2`.
- Brain Hub fails because its literal-only AST reader does not recognize the canonical derived phase list; committed Wiki artifact readback independently detects exact reproducibility drift. These are separate bounded mechanisms: `wave2-docs-first-blocker-j2`, `wave2-order-canary-and-exact-wiki-j5`.

No skip/xfail, test-assertion weakening, source repair, or real model experiment was added by this diagnostic continuation. The probes use existing tests, injected transports and explicit network-denial where applicable. Test fixtures' local Git/temporary-file activity is not a production integration claim.

## Reuse and next gates

The five already-created follow-ups remain #1280 (N30R v1 canonical identity), #1281 (OCI profile lock), #1282 (Tuple import), #1283 (CLI executable fixture), and #1284 (Git test identity). #1281 now additionally owns the two proven HTTP consumers. Existing #419/#432/#653/#889 ownership is not broadened from keyword similarity. New Stage1 caller-admission findings name #889 as adjacent for exact overlap review, not automatically the same implementation scope.

Each packet carries node IDs, exact source/trace basis, read scope, proposed bounded repair scope where known, verification requirements and a next gate. Sensitive authority/identity changes require a separately settled repair contract; unresolved test isolation requires capturing the missing original blocker. Do not launch 119 repairs or create 119 duplicate issues from this count.

Wave 1 is separately complete at draft PR #407, head `d512057d54f4d451ba62da07da4173f90e9ad966`, with 120 focused/adjacent passes and required CI success. It has not been merged and does not make the full repository green.

## Freshness

The full run binds immutable source `199feb12...`. During the work main advanced first to `9b873ba...`, then `ac42aa9...`, then `260184bb789b8be5038d9530f659da1a00c611e4`. The earlier six research/workflow paths have a retained 12-test affected-delta supplement; this is not another full suite.

`source_freshness` records all ten changed paths through `260184bb...`, all diagnostic source-blob identities and bounded AST readback of the changed owner files. The examined contract rehydration, cleanup-authority, lease-identity, lease-ID and cleanup methods are AST-equivalent. New public claim and cross-entrypoint conflict-admission behavior is not covered by the old full run. Retain the full-run observations; recheck changed entrypoint behavior before a corresponding repair/merge. Do not rebase or replace the evidence PR merely to chase an advancing main.

## Files and integrity

- `inventory.json`: immutable exact historical/current evidence inventory. SHA-256 `d24f98a6c559cc9f2c284244908291a512f67d8684173b0a192ef440e6c97e40`.
- `disposition.json`: 840 dispositions, 119 packets, 101 new source/trace adjudications, owner bindings, residual questions and freshness. SHA-256 `0a8aff878f4c4f5f443662cdc8d46dab5c9ddfa5c091ff0e70e1c6abf03c2b30`.
- Prior disposition bytes remain in commit `fe3fd5e6f0f91b4898bc53398295e3d6df8a499c`, SHA-256 `b6daf7b0bbd2787612c613470821c1a85c9d3027806f72fbec45776772be0370`.

Scope is exactly these three diagnostic paths; this continuation changes README/disposition and preserves inventory. A deterministic readback must validate unique/equal node sets, 467 exact packet assignments, owner presence, summary counts, source/line/hash integrity and no escaped write scope before commit. Native DevSpace Candidate provenance and this report do not constitute independent acceptance, runtime deployment, or completion certification.
