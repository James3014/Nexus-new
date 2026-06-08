# ADR-010: Context-Budget Aware Surgical Localization

## Status
PROPOSED

## Date
2026-06-06

## Context
In previous task attempts (notably `astropy-12907`), the `Localizer` failed due to:
1. **Truncation Drift**: Hardcoded `top_k=3` excluded relevant functions (`_cstack`) from the context.
2. **Context Pollution**: Diagnostic headers (`## Primary Target`) induced `SEARCH_MISMATCH` in LLM search/replace blocks.
3. **Monolithic Coupling**: Ranking, AST parsing, and prompting were intermingled, making it hard to apply sophisticated scoring strategies (like Keyword Boosting).

## Decision
Refactor the `Localizer` into a modular **Surgical Intelligence Suite** consisting of:
1. **`Retriever`**: Responsible for coarse-grained file ranking using BM25.
2. **`Slicer` (The Surgical Knife)**: Uses AST to extract functional entities and scores them dynamically.
3. **`Packer` (Budget Manager)**: Dynamically assembles the prompt context based on a token/line budget instead of a static count.
4. **`PromptSanitizer`**: Ensures only pure source code (with minimal file path comments) is delivered to the model.

## Alternatives Considered
- **Simply increasing `top_k`**: Rejected. This is a magic number patch and doesn't solve context pollution or scale to larger files.
- **Using a larger context model**: Rejected. Larger context often increases "Lost in the Middle" issues and dilutes the signal. Precision slicing is always superior (Linus Principle).

## Consequences
- **Positive**: 100% elimination of `SEARCH_MISMATCH` caused by internal metadata.
- **Positive**: Dynamic inclusion of all logically relevant functions mentioned in the problem statement.
- **Negative**: Increased complexity in the `local_heal` codebase.
- **Verification**: Will be implemented using TDD to ensure parity and improvement over the current baseline.
