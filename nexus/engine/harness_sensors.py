"""Alias of ``nexus_runtime.planning.engine.harness_sensors``; the planner source is owned by nexus-runtime (D2, Phase 4b)."""

import importlib
import sys
from typing import TYPE_CHECKING

from nexus_runtime._compat_aliases import install_alias

if TYPE_CHECKING:  # static re-export for type checkers; runtime identity comes from the alias below
    from nexus_runtime.planning.engine.harness_sensors import *  # noqa: F403  # pyright: ignore[reportWildcardImportFromLibrary]

install_alias(__name__, "nexus_runtime.planning.engine.harness_sensors")
sys.modules[__name__] = importlib.import_module("nexus_runtime.planning.engine.harness_sensors")
