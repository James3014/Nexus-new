#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path

from nexus.services.patcher import SafePatcher


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "smoke@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "smoke"], cwd=root, check=True)

        f = root / "a.txt"
        f.write_text("old\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        patch = """--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-old
+new
"""
        violations = [{"file": "a.txt", "patch": patch, "reason": "write-path-smoke"}]
        patcher = SafePatcher(lock_dir=str(root), project_root=str(root))
        ok = patcher.apply(violations)

        content = f.read_text(encoding="utf-8").strip()
        if not ok or content != "new":
            print("❌ WRITE_PATH_SMOKE FAIL")
            return 1

    print("✅ WRITE_PATH_SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
