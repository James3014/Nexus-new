#!/usr/bin/env python3
"""Portable repository-root resolution for scripts/bench entrypoints.

Derives the checkout root from this module's own location so restored
regression entrypoints and the AV substrate generator no longer depend on
machine-specific absolute paths.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fail closed if the derived root does not actually contain this module.
if not (REPO_ROOT / "scripts" / "bench" / "_repo_root.py").is_file():
    raise RuntimeError(
        f"Derived REPO_ROOT is not a Nexus checkout containing scripts/bench: {REPO_ROOT}"
    )
