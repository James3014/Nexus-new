"""Alias of ``nexus_runtime.support.contracts.canonical_execution``; the planner source is owned by nexus-runtime (D2, Phase 4b)."""
import importlib
import sys

from nexus_runtime._compat_aliases import install_alias

install_alias(__name__, "nexus_runtime.support.contracts.canonical_execution")
sys.modules[__name__] = importlib.import_module("nexus_runtime.support.contracts.canonical_execution")
