#!/usr/bin/env python3
"""將 root 下的 nexus-auto-repair-*.yaml 遷移至 .nexus/records/auto-repair/"""
import shutil
from pathlib import Path
from datetime import datetime

def archive(repo_root: Path):
    dest = repo_root / ".nexus" / "records" / "auto-repair"
    dest.mkdir(parents=True, exist_ok=True)

    yamls = sorted(repo_root.glob("nexus-auto-repair-*.yaml"))
    for y in yamls:
        mtime = datetime.fromtimestamp(y.stat().st_mtime)
        sub = dest / mtime.strftime("%Y-%m")
        sub.mkdir(exist_ok=True)
        shutil.move(str(y), str(sub / y.name))

    print(f"Archived {len(yamls)} YAML files")

if __name__ == "__main__":
    archive(Path(__file__).resolve().parent.parent.parent)
