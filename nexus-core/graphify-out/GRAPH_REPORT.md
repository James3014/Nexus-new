# Graph Report - nexus-core  (2026-05-27)

## Corpus Check
- 2 files · ~900 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 14 nodes · 19 edges · 2 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b07f0eb6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]

## God Nodes (most connected - your core abstractions)
1. `get_public_api_signatures()` - 5 edges
2. `check_pub_api_diff()` - 3 edges
3. `scan_and_diagnose()` - 2 edges
4. `test_rust_ast_scan_and_diagnose()` - 2 edges
5. `test_rust_ast_diff_caching()` - 2 edges
6. `test_rust_ast_diff_syntax_fault_tolerance()` - 2 edges
7. `get_source_hash()` - 2 edges
8. `extract_fuzzy_signatures()` - 2 edges
9. `format_signature()` - 2 edges
10. `compare_pub_apis()` - 2 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities (2 total, 0 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.48
Nodes (5): compare_pub_apis(), extract_fuzzy_signatures(), format_signature(), get_public_api_signatures(), get_source_hash()

### Community 1 - "Community 1"
Cohesion: 0.43
Nodes (5): check_pub_api_diff(), scan_and_diagnose(), test_rust_ast_diff_caching(), test_rust_ast_diff_syntax_fault_tolerance(), test_rust_ast_scan_and_diagnose()

## Suggested Questions
_Not enough signal to generate questions. This usually means the corpus has no AMBIGUOUS edges, no bridge nodes, no INFERRED relationships, and all communities are tightly cohesive. Add more files or run with --mode deep to extract richer edges._