#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.engine.nexus_cli import nexus as main
from nexus.services.cli_commands_service import CliCommandsService

class NexusCLI(CliCommandsService):
    """⚔️ Legacy Compatibility Shim for NexusCLI (AOS 145+)"""
    def __init__(self, *args, **kwargs):
        # 兼容舊版 tests/test_v9_regression_p1.py 的 project_root 傳參內容
        root = kwargs.pop("project_root", None) or (args[0] if args else None)
        super().__init__(repo_root=root)

if __name__ == "__main__":
    main()
