"""
DEPRECATED: Use GranularMethodLocalizer instead.

This module is no longer used by the pipeline.
Kept for reference only. All functionality has been moved to:
- granular_localizer.py (BM25 + AST localization)
- function_localizer.py (AST-based function extraction)
"""


def _deprecated_guard():
    raise RuntimeError(
        "DEPRECATED: localizer.py is no longer used by the pipeline. "
        "Use nexus.services.local_heal.granular_localizer.GranularMethodLocalizer instead."
    )
