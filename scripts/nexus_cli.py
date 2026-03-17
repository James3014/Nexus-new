#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.engine.nexus_cli import main, NexusCLI

if __name__ == "__main__":
    main()
