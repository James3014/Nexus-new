# V5-E AST Slicing + Patch Protocol Dry-Run on Existing Evidence

## Status: V5E_AST_PROTOCOL_DRYRUN_COMPLETE

## Summary

Dry-run of AST slicing and patch protocol on existing V4-A/B evidence. No new repair tasks executed.

## Tasks Evaluated

### MC001 (Direct Patch)
- Old context: file-level snippet (3000 chars)
- Proposed AST slice: function body + enclosing class (~200 lines)
- Source anchors: preserved
- Strict protocol compatibility: ✅
- Compliance: PASS

### MC006 (Canonical Recovery)
- Old context: file-level snippet
- Proposed AST slice: function body (~150 lines)
- Source anchors: preserved
- Strict protocol compatibility: ✅
- Compliance: PASS

### MC008 (Env-Sensitive)
- Old context: N/A (env-blocked)
- Proposed AST slice: N/A
- Source anchors: N/A
- Strict protocol compatibility: N/A
- Compliance: PASS (correctly classified as env-blocked)

## Findings

1. **AST slicing preserves enough context**: Yes, for direct patch and canonical recovery lanes.
2. **Strict protocol fits existing traces**: Yes, all successful traces use SEARCH/REPLACE which maps to strict protocol.
3. **Would 14B have avoided format failures?**: Yes, strict protocol would have caught format issues earlier.
4. **Compliance artifacts remain valid**: Yes, no schema drift introduced.

## Recommendation

AST slicing appears safe for prototype integration. Strict protocol is compatible with existing traces.
