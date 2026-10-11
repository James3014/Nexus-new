"""Alias of ``nexus_runtime.planning.services.runtime_workforce_admission``; the planner source is owned by nexus-runtime (D2, Phase 4b)."""

import importlib
import sys
from typing import TYPE_CHECKING

from nexus_runtime._compat_aliases import install_alias

if TYPE_CHECKING:  # static re-export for type checkers; runtime identity comes from the alias below
    from nexus_runtime.planning.services.runtime_workforce_admission import *  # noqa: F403  # pyright: ignore[reportWildcardImportFromLibrary]
    from nexus_runtime.planning.services.runtime_workforce_admission import (
        _binding_payload as _binding_payload,
    )
    from nexus_runtime.planning.services.runtime_workforce_admission import (
        _decision_dict as _decision_dict,
    )
    from nexus_runtime.planning.services.runtime_workforce_admission import (
        _sha256_json as _sha256_json,
    )

install_alias(__name__, "nexus_runtime.planning.services.runtime_workforce_admission")
sys.modules[__name__] = importlib.import_module(
    "nexus_runtime.planning.services.runtime_workforce_admission"
)
