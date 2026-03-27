#!/usr/bin/env python3
"""
Deprecated compatibility shim.

Canonical router implementation is:
  - nexus/core/router.py

Keep this module only to avoid breaking old imports.
"""

from __future__ import annotations

import warnings

from nexus.core.router import SkillsRouter as _CanonicalSkillsRouter

warnings.warn(
    "scripts/core/skills_router.py is deprecated; use nexus/core/router.py instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Backward-compatible export
SkillsRouter = _CanonicalSkillsRouter


if __name__ == "__main__":
    import json
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    router = SkillsRouter(project_root=str(project_root))
    demo = router.route("R", {"task_id": "debug leak", "files": ["app.py", "test_app.py"]})
    print(json.dumps(demo, ensure_ascii=False, indent=2))

