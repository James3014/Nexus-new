"""Single inventory + resolver for the LanceDB roots under ``<project>/.nexus``.

Inventory only: this module does NOT migrate data and does not merge the roots.
Each root below is a separate store with its own owner; call sites should resolve
the path here instead of hardcoding it.

| kind          | relative path                          | owner / main users                                   | env override            |
|---------------|----------------------------------------|------------------------------------------------------|-------------------------|
| KNOWLEDGE     | .nexus/knowledge/lancedb               | services/memory.py (MemoryService), nexus_fs.py      | NEXUS_MEMORY_DB_PATH    |
| MEMORY_INDEX  | .nexus/memory/memory_index.lancedb     | research/findings_vector_sync.py (writes findings_   | NEXUS_MEMORY_DB_PATH    |
|               |                                        | cards), local_heal/memory_retrieval_adapter.py       |                         |
|               |                                        | (reads them, #2640), core/router.py,                 |                         |
|               |                                        | memory_indexer.py, msa_indexer.py                    |                         |
| REPOSITORY    | .nexus/memory_repository               | legacy: no caller since #2640 (the findings reader   | none                    |
|               |                                        | moved to MEMORY_INDEX, where the writer is)          |                         |
| VECTOR_DB     | .nexus/vector_db                       | core/vector_rag.py, learning/vector_cache.py,        | none                    |
|               |                                        | storage_implementations.py, nexus_fs.py              |                         |
| TENANT_JSONL  | .nexus/tenants/<tenant>/lancedb/*.jsonl| infrastructure/storage_implementations.py (JSONL,    | none                    |
|               |                                        | NOT a LanceDB dataset despite the directory name)    |                         |

NEXUS_MEMORY_DB_PATH is honored today by KNOWLEDGE (MemoryService) and MEMORY_INDEX
(FindingsVectorSync); both read the same variable with different defaults, so setting
it points the two stores at one path. ``resolve_lancedb_root`` keeps that behaviour.
"""

import os
from pathlib import Path
from typing import Optional, Union

from nexus.core.state_root import persistent_state_root

MEMORY_DB_PATH_ENV = "NEXUS_MEMORY_DB_PATH"

KNOWLEDGE = "knowledge"
MEMORY_INDEX = "memory_index"
REPOSITORY = "repository"
VECTOR_DB = "vector_db"
TENANT_JSONL = "tenant_jsonl"

LANCEDB_ROOT_RELPATHS = {
    KNOWLEDGE: Path(".nexus") / "knowledge" / "lancedb",
    MEMORY_INDEX: Path(".nexus") / "memory" / "memory_index.lancedb",
    REPOSITORY: Path(".nexus") / "memory_repository",
    VECTOR_DB: Path(".nexus") / "vector_db",
    TENANT_JSONL: Path(".nexus") / "tenants",
}

# Kinds whose current call sites honor NEXUS_MEMORY_DB_PATH.
_ENV_OVERRIDE_KINDS = frozenset({KNOWLEDGE, MEMORY_INDEX})


def resolve_lancedb_root(
    kind: str,
    project_root: Union[str, Path],
    tenant_id: Optional[str] = None,
    honor_env: bool = True,
) -> Path:
    """Return the root path for ``kind`` (same path the legacy hardcoded call sites build).

    TENANT_JSONL needs ``tenant_id`` and returns ``.nexus/tenants/<tenant_id>/lancedb``.
    """
    if kind not in LANCEDB_ROOT_RELPATHS:
        raise ValueError(f"Unknown LanceDB root kind: {kind!r}")
    if honor_env and kind in _ENV_OVERRIDE_KINDS:
        override = os.environ.get(MEMORY_DB_PATH_ENV)
        if override:
            return Path(override)
    root = Path(persistent_state_root(project_root))  # #2688
    if kind == TENANT_JSONL:
        if not tenant_id:
            raise ValueError("tenant_id is required for the TENANT_JSONL root")
        return root / LANCEDB_ROOT_RELPATHS[kind] / tenant_id / "lancedb"
    return root / LANCEDB_ROOT_RELPATHS[kind]
