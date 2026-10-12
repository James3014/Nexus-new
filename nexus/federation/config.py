from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import json

import warnings as _archived_warnings

_archived_warnings.warn(
    "ARCHIVED 2026-10-12 (#1850): stub federation package; see ARCHIVED_2026-10-12.md. "
    "Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)

FEDERATION_CONFIG = "workspaces/federation_config.json"

def get_federation_config(project_root: Optional[Path] = None) -> Dict[str, List[str]]:
    base_dir = project_root or Path.cwd()
    config_path = base_dir / FEDERATION_CONFIG
    
    if not config_path.exists():
        return {}
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_tenant_repos(tenant_id: str, project_root: Optional[Path] = None) -> List[str]:
    config = get_federation_config(project_root)
    return config.get(tenant_id, [])
