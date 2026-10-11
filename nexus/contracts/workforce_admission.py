"""Alias of ``nexus_runtime.planning.contracts.workforce_admission``; the planner source is owned by nexus-runtime (D2, Phase 4b)."""
import importlib
import sys

from nexus_runtime._compat_aliases import install_alias

install_alias(__name__, "nexus_runtime.planning.contracts.workforce_admission")
sys.modules[__name__] = importlib.import_module("nexus_runtime.planning.contracts.workforce_admission")
