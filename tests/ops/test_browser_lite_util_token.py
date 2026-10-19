"""browser_lite_util reads its bearer from the environment, never from source (#2678)."""

import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "browser_lite_util.py"


def test_source_has_no_hardcoded_bearer() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'os.environ.get("NEXUS_BROWSER_MCP_TOKEN", "")' in source
    assert not re.search(r"""TOKEN\s*=\s*["'][A-Za-z0-9_\-]{16,}["']""", source)


def test_missing_token_exits_before_any_request() -> None:
    env = {"PATH": "/usr/bin:/bin", "NEXUS_BROWSER_MCP_TOKEN": ""}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "tabs_list"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert "NEXUS_BROWSER_MCP_TOKEN" in result.stdout
