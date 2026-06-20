"""
WorkspaceProvisionRecipe v1.0

Deterministic workspace provisioning checks before reproduction.
Verifies: repo root exists, writable, test fixtures present, critical paths accessible.
Supports auto-provisioning via SWE-bench repo_map.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict


# SWE-bench repo map for auto-provisioning
SWE_BENCH_REPO_MAP: Dict[str, str] = {
    "astropy": "https://github.com/astropy/astropy.git",
    "django": "https://github.com/django/django.git",
    "requests": "https://github.com/psf/requests.git",
    "flask": "https://github.com/pallets/flask.git",
    "sympy": "https://github.com/sympy/sympy.git",
    "pytest": "https://github.com/pytest-dev/pytest.git",
    "matplotlib": "https://github.com/matplotlib/matplotlib.git",
    "scikit-learn": "https://github.com/scikit-learn/scikit-learn.git",
    "sphinx": "https://github.com/sphinx-doc/sphinx.git",
    "black": "https://github.com/psf/black.git",
    "click": "https://github.com/pallets/click.git",
    "httpie": "https://github.com/httpie/cli.git",
    "sqlalchemy": "https://github.com/sqlalchemy/sqlalchemy.git",
    "xarray": "https://github.com/pydata/xarray.git",
    "marshmallow": "https://github.com/marshmallow-code/marshmallow.git",
    "pydantic": "https://github.com/pydantic/pydantic.git",
    "fastapi": "https://github.com/tiangolo/fastapi.git",
    "scrapy": "https://github.com/scrapy/scrapy.git",
}


@dataclass
class WorkspaceProvisionResult:
    """Result of workspace provisioning check."""
    ready: bool
    repo_root_exists: bool = False
    repro_script_exists: bool = False
    test_assets_present: bool = False
    critical_paths_ok: bool = False
    missing_items: List[str] = field(default_factory=list)
    failure_reason: str = ""
    auto_provisioned: bool = False
    
    @property
    def can_enter_repro(self) -> bool:
        return self.ready and self.repo_root_exists


class WorkspaceProvisionChecker:
    """
    Pre-flight checker that verifies workspace readiness before reproduction.
    Supports auto-provisioning: if workspace is missing, clones from SWE-bench repo_map.
    """
    
    @staticmethod
    def check(repo_dir: Path, instance_id: str = "") -> WorkspaceProvisionResult:
        """Check if workspace is ready for reproduction. Auto-provisions if missing."""
        missing = []
        auto_provisioned = False
        
        # 1. Check repo root exists and is accessible
        repo_root_exists = repo_dir.exists() and repo_dir.is_dir()
        
        # 2. Auto-provision if missing
        if not repo_root_exists:
            repo_key = next((k for k in SWE_BENCH_REPO_MAP if k in instance_id), None)
            if repo_key:
                try:
                    repo_dir.parent.mkdir(parents=True, exist_ok=True)
                    res = subprocess.run(
                        ["git", "clone", SWE_BENCH_REPO_MAP[repo_key], str(repo_dir)],
                        capture_output=True, text=True, timeout=300
                    )
                    if res.returncode == 0:
                        repo_root_exists = True
                        auto_provisioned = True
                    else:
                        missing.append(f"repo_clone_failed:{res.stderr[:200]}")
                except Exception as e:
                    missing.append(f"repo_clone_error:{str(e)[:200]}")
            else:
                missing.append(f"repo_root:{repo_dir}")
        
        # 3. Check workspace is writable
        workspace_writable = False
        if repo_root_exists:
            try:
                test_file = repo_dir / ".nexus_workspace_test"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink()
                workspace_writable = True
            except Exception:
                missing.append("workspace:not writable")
        
        # 4. Check reproduce script (may not exist yet — LLM generates it)
        repro_script = repo_dir / "reproduce_bug.py"
        repro_script_exists = repro_script.exists()
        
        # 5. Check test assets
        test_files = list(repo_dir.glob("test_*.py")) + list(repo_dir.glob("*_test.py"))
        test_assets_present = len(test_files) > 0
        if not test_assets_present:
            test_files = list(repo_dir.rglob("test_*.py"))[:5]
            test_assets_present = len(test_files) > 0
        
        # 6. Check critical paths
        critical_files = ["setup.py", "pyproject.toml", "setup.cfg", "requirements.txt"]
        critical_paths_ok = any((repo_dir / f).exists() for f in critical_files)
        
        # Determine readiness
        ready = repo_root_exists and workspace_writable
        
        failure_reason = ""
        if not ready:
            if not repo_root_exists:
                failure_reason = "REPO_NOT_MOUNTED"
            elif not workspace_writable:
                failure_reason = "REPO_NOT_WRITABLE"
        
        return WorkspaceProvisionResult(
            ready=ready,
            repo_root_exists=repo_root_exists,
            repro_script_exists=repro_script_exists,
            test_assets_present=test_assets_present,
            critical_paths_ok=critical_paths_ok,
            missing_items=missing,
            failure_reason=failure_reason,
            auto_provisioned=auto_provisioned,
        )
