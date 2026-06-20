# V5-B AST Context Slicing Prototype

## Status: V5B_AST_CONTEXT_SLICING_PROTOTYPE_READY

## Summary

Prototype AST context slicing implemented in `nexus/services/local_heal/context_slicer.py`.

## Implementation

```python
class ContextSlice:
    file_path: str
    symbol_name: str
    start_line: int
    end_line: int
    source_hash: str
    extracted_text: str
    extraction_method: str  # ast_symbol / line_block / fallback
    is_exact: bool
    enclosing_class: str | None

class ContextSlicer:
    def slice_symbol(source_path, symbol_hint, max_lines=100) -> ContextSlice
    def slice_line_range(source_path, start, end, max_lines=100) -> ContextSlice
    def slice_from_error(source_path, error_line, context=5) -> ContextSlice
    def fallback_to_file(source_path, max_lines=200) -> ContextSlice
```

## Prototype Modes

1. **Exact symbol mode**: Uses `ast.parse()` to find function/class by name
2. **Line-span mode**: Extracts line range with natural boundaries
3. **Test-failure stack-frame mode**: Extracts from error line ± context
4. **Fallback mode**: Returns file-level snippet with truncation

## Tests

| Test | Status |
|------|--------|
| extracts function slice | ✅ |
| extracts method slice with enclosing class | ✅ |
| records source hash | ✅ |
| refuses stale source if hash mismatch | ✅ |
| falls back when symbol missing | ✅ |
| bounded output respects token/line budget | ✅ |
| preserves file path and line span | ✅ |
| does not include whole file when slice is enough | ✅ |

## Files

- `nexus/services/local_heal/context_slicer.py` — prototype implementation
- `tests/unit/local_heal/test_context_slicer.py` — 8 tests

## Fallback Path

If AST slicing fails (parse error, symbol not found), falls back to file-level snippet with source hash preservation. No silent degradation.
