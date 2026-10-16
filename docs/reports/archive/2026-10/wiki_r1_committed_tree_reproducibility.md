# WIKI-R1 Committed-Tree Reproducibility Gate Report

## Status: BASELINE

## Target SHA
`c58bae1ad95d3b3e134a60b1ee90ed4ae1e9acf3`

## Root Cause
Generated retrieval artifacts (`agent-index.json`, `llms.txt`, `wikilink-graph.json`) were built from a dirty worktree containing uncommitted Wiki source changes. The committed HEAD contained different source content, causing the checked-in artifacts to differ from what a clean committed-tree rebuild would produce.

## Drifted Artifacts
- `agent-index.json`: source_fingerprint changed
- `wikilink-graph.json`: source_fingerprint changed
- `llms.txt`: no drift

## Resolution
1. Added `check_wiki_committed_reproducibility.py` - rebuilds from committed Git ref sources in a temporary directory
2. Added 7 focused tests for reproducibility verification
3. Updated Governance Charter with committed-tree reproducibility gate requirement
4. Added lesson to Learning Closure Matrix
