# V5-A AST-Level Context Slicing Plan

## Status: V5A_AST_SLICING_READY_FOR_PROTOTYPE

## 1. Current Retrieval Path

- `nexus/services/local_heal/localizer.py` — file ranking/localization
- `nexus/services/local_heal/granular_localizer.py` — GranularMethodLocalizer
- `nexus/services/local_heal/ast_locator.py` — AST-based symbol location
- `nexus/services/local_heal/context.py` — context construction
- `nexus/services/local_heal/context_budget.py` — token budget enforcement
- Current max_files enforced in `context.py` (default: 4 files)

## 2. AST Slicing Target Design

### Slice Units
- **Function/method body**: primary slice for repair context
- **Enclosing class**: included when method is target
- **Direct imports**: included for type/type hint resolution
- **Direct dependency signatures**: included for API surface awareness
- **Test failure stack frame symbol**: targeted from error evidence
- **Neighboring definitions**: included only when budget allows

### Slice Hierarchy
```
File → Class → Method → Body
         ↓
      Imports
         ↓
   Dependency signatures (if cheap)
```

## 3. Context Budget Policy

| Parameter | 7B Default | 14B Fallback |
|-----------|-----------|--------------|
| max_files | 4 | 6 |
| max_tokens | 6000 | 10000 |
| max_ast_nodes | 500 | 1000 |
| mandatory_source_anchors | yes | yes |
| fallback_to_file_level | yes | yes |

## 4. Safety and Attribution Requirements

Each slice must preserve:
- `file_path`: absolute path
- `symbol_name`: function/class name
- `start_line`, `end_line`: line span
- `source_hash`: SHA256 of source file
- `extraction_method`: ast_symbol / line_block / fallback
- `caller_callee_relation`: if available
- `is_exact`: boolean (exact AST vs heuristic)

## 5. Integration Options

| Option | Status | Notes |
|--------|--------|-------|
| Python ast module | Available | Already used in patch_applier.py |
| libcst | Not installed | Could add for CST-level fidelity |
| tree-sitter | Not available | Would need install |
| Existing Nexus code intel | Available | ast_locator.py, granular_localizer.py |
| Serena/MCP | Not available | External dependency |

**Recommendation**: Use existing Python ast module + ast_locator.py. No new dependencies needed.

## 6. Risk Analysis

| Risk | Mitigation |
|------|-----------|
| Incomplete slice | Fallback to file-level snippet |
| Too-small slice | Include enclosing class + imports |
| Wrong symbol selected | Source hash verification |
| Stale source hash | Re-read and re-hash before slice |
| Cross-file dependency | Include import signatures |
| Tests require broader context | Budget expansion for test files |

## Recommendation

**V5A_AST_SLICING_READY_FOR_PROTOTYPE** — bounded prototype with existing Python ast, no new dependencies.
