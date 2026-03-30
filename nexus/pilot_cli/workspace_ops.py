import os
import re
import subprocess
from pathlib import Path
from typing import Optional


def is_repo_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("git@")


def infer_repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    return name or "repo"


def default_clone_dir(tenant_id: str, repo_url: str) -> Path:
    root = Path(os.getenv("NEXUS_PILOT_WORKSPACE_ROOT", str(Path.home() / "nexus-pilot-workspaces")))
    return root / (tenant_id or "anonymous-tenant") / infer_repo_name(repo_url)


def clone_repo(repo_url: str, tenant_id: str, dest: Optional[str] = None) -> Path:
    target = Path(dest).expanduser() if dest else default_clone_dir(tenant_id, repo_url)
    if target.exists():
        raise RuntimeError(f"Target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "clone", repo_url, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git clone failed")
    return target
