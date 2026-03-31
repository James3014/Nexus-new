#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> str:
    r = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return r.stdout.strip()


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    allowed = {
        "nexus/services/",
        "nexus/engine/",
        "nexus/core/",
        "scripts/ops/",
        "scripts/engine/",
        "scripts/bench/",
        "scripts/Templates/",
        "tests/",
        "docs/",
    }
    ignored = {
        "ci_benchmark.csv",
        "task_manifest.yaml",
        "muse_nexus.egg-info/",
        "worktrees/",
        "benchmarks/click",
    }
    changed = run(["git", "diff", "--name-only", "HEAD"], repo).splitlines()
    violations = [
        p
        for p in changed
        if p
        and not any(p.startswith(a) for a in allowed)
        and not any(p.startswith(i) for i in ignored)
    ]

    if violations:
        print("❌ SCOPE_GUARD FAIL")
        for v in violations:
            print(f"- {v}")
        return 1

    print("✅ SCOPE_GUARD PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
