from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


def test_nexus_group_command_names_are_unique() -> None:
    cli_path = Path(__file__).resolve().parents[1] / "scripts" / "engine" / "nexus_cli.py"
    text = cli_path.read_text(encoding="utf-8")
    names = re.findall(r'@nexus_group\.command\(name="([^"]+)"\)', text)
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    assert duplicates == [], f"duplicate command registrations found: {duplicates}"
