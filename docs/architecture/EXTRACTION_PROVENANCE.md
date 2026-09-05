# Extraction Provenance

Source Repository: `James3014/Nexus-new`
Base Commit: `8e8e02911c888d4c8a4667d4b5dd13df85c20cfd`
Base Tree: `78da10b2402f8c25f4d04ae5b470e7c10bd984f7`
Extraction Date: 2026-09-06T07:12:47Z

## Extraction Targets
1. **James3014/nexus-open-swe-runtime**
   - Strategy: `git subtree split` (history preserving)
   - Canonical prefix: `runtimes/open_swe`
   - Initial SHA: `54e75af6`
   - Status: Verified standalone, 71 tests passed, 0 coupling to Nexus-new.

2. **James3014/nexus-core**
   - Strategy: `clean snapshot extraction`
   - Canonical prefixes: `product/`, `tests/product/`, `tests/benchmark/test_core_v1_*`
   - Initial SHA: `2c6568e`
   - Status: Verified standalone, 974 tests passed, wheel build & install verified.

3. **James3014/nexus-learning**
   - Strategy: `selective canonical extraction`
   - Canonical modules: `learning_episode_projection`, `learning_closure_effectiveness`, `learning_effectiveness_measurement`, `learning_coverage_contract`, `learning_coverage_probes`, `outcome_memory`, `retrieval_audit`, `contracts/learning_experience`
   - Initial SHA: `139bb21`
   - Status: Verified standalone, 142 tests passed, no runtime/planner authority.

## Legacy Code Deletion Policy
First-phase deletion in `James3014/Nexus-new` is strictly forbidden.
All legacy code remains intact during extraction to support backward compatibility until consumer migration PRs are executed.
