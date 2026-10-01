# Issue 330 - Tier 3 evidence rebind, 2026-10-01

This is diagnostic evidence, not repair, acceptance, merge or production authority. AUTO_CHAIN=false. Issue #330 remains open.

## Bound executions

| Evidence | Immutable identity | Result |
|---|---|---|
| Historical full Tier 3 | run 31925711602; job 95112840837; source 52927467b1404e71058b6aef4fed8f4e8f51c62a | 746 failed, 5 errors, 13,126 passed, 36 skipped |
| Fresh manual full Tier 3 | run 36837565415; job 110288592865; source 199feb12fdd9726684785d5420e6b48da03a155f | 462 failed, 5 errors, 18,212 passed, 37 skipped, 1 deselected |
| Current-main delta supplement | main 9b873ba0c057dcdc064327b35adc1076ffacd288 | 12 affected tests passed; not another full Tier 3 run |

The manual run uses the repository's full-regression workflow, not PR/push impact-only CI. Its 18,716 JUnit cases have complete status accounting. The one deselected case is reported, not silently counted as a pass.

Historical artifact 9257930120 now returns HTTP 404. Its original JUnit was not recovered. Instead, the exact historical job log was recovered and all 751 failure/error summary records were parsed. The raw job log SHA-256 is 96ef0ef63725d9cce3a58a9bb25b012b3c79e93d129d339ade3a645adba0b940. This fallback does not manufacture the missing XML.

Current artifact 11151528361 contains full-regression.xml. ZIP SHA-256: 063cf67dfe9a3514891f5e9efb692744c6d14dcf6b2e659c3705f208eafcb302. The ZIP hash is recorded from actual bytes in inventory.json; the XML SHA-256 is 11ffa9063750b544db847a93eeedbbe5a8e38cd9c7d03697ac8b63bd2662400b.

## Exact node comparison

All 751 historical failure/error node IDs map to current JUnit cases: 373 now pass, 373 still fail, and 5 still error. Current failures additionally contain 89 node IDs absent from the historical failure list. These 89 are newly observed failures, not automatically newly introduced regressions. The union is 840 unique nodes with no missing or duplicate disposition rows.

## Calibrated disposition

- ALREADY_FIXED: 373 exact historical nodes now pass. A unique fixing commit was not established for every node.
- TEST_OR_ENV_DEFECT: 93 current failures with explicit fixture/environment evidence.
- EXISTING_ISSUE_OWNS_IT: 12 current failures mapped narrowly to #419, #432, #653 or #889.
- CURRENT_DEFECT: 362 current source/test-contract failures. Of these, 42 have a source cause identified; 320 still require causal source-versus-oracle adjudication across 111 test modules.

CURRENT_DEFECT is a reproduction-level classification, not a claim that all 362 are production bugs. The 320 unresolved cases are marked CAUSAL_ADJUDICATION_REQUIRED, have read-only bounded investigation packets, and grant no repair scope. Consequently this packet completes the full-run inventory and triage matrix, but does NOT claim all causal ownership or all future repair contracts are resolved. Do not close #330 or call the repository green.

## Proven bounded follow-ups

| Follow-up | Current cases | Evidence |
|---|---:|---|
| #1280 N30R v1 canonical execution/evidence binding | 6 | Pipeline/verifier reached; invalid/missing canonical identity prevents candidate projection |
| #1281 OCI profile/uv.lock integrity subject | 35 | Profile declares a different uv.lock hash; correct fail-closed rejection |
| #1282 AmbiguityGuard annotation import | 3 | Unbound Tuple at import, before policy execution |
| #1283 P0T5 registered CLI resolver fixture | 17 | Actual binary resolver runs before the injected fake runner |
| #1284 isolated Git fixture author identity | 4 errors | Fixture disables global config and supplies no author; exact stderr confirms failure |

These issues are evidence-bound follow-up contracts, not dispatched third-wave work. Other proven fixture families and unresolved source/oracle cases remain explicitly enumerated in disposition.json under bounded read scopes. Do not create a broad repository repair from the aggregate count.

## Files and validation

inventory.json binds source/run/job/artifact hashes and preserves each union node's historical/current outcome, failure message and traceback hash/frame references. disposition.json supplies one triage disposition per node, proof level, exact owner/follow-up when supported, and bounded investigation packets. It explicitly records that not all causal roots are proven.

File SHA-256: inventory.json = d24f98a6c559cc9f2c284244908291a512f67d8684173b0a192ef440e6c97e40; disposition.json = b6daf7b0bbd2787612c613470821c1a85c9d3027806f72fbec45776772be0370. The data files were generated from the authenticated job log/JUnit bytes through bounded Remote Desktop Commander analysis; this is data-generation transport, not Core acceptance authority.

The JSON record sets must be equal, contain 840 unique nodes, account for all 467 current failures/errors, and match the 373 historical-to-pass transitions. Historical and current denominators are different; no failure-rate improvement or model-effectiveness claim follows from these counts.

## Main movement and next gate

The full run was dispatched on exact then-current main 199feb12. Main advanced to 9b873ba in six research/workflow paths while it ran. Their exact contents are present unchanged on integrated PR #407 head 26d38568882815a79df60d3d801335b6b32dc0b8; the two affected test files passed 12 tests. This supplement does not convert the old full-run result into an all-suite result on the newer SHA.

Next gate: adjudicate the unresolved bounded source/oracle packets and authorize only proven minimal repairs; separately review Wave 1 draft PR #407. No provider/model execution, source/test assertion suppression, merge, runtime activation or automatic successor dispatch was performed for Wave 2.
