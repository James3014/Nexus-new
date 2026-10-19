"""browser_lite_util reads its bearer from the environment, never from source (#2678)."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "browser_lite_util.py"


def test_source_has_no_hardcoded_bearer() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert re.search(
        r"""os\.environ\.get\(\s*["']NEXUS_BROWSER_MCP_TOKEN["']\s*,\s*["']["']\s*\)""", source
    )
    # No long token-like string literal anywhere in the script.
    assert not re.search(r"""["'][A-Za-z0-9_\-]{32,}["']""", source)
    assert 'MCP_URL = "http://127.0.0.1:12307/mcp"' in source


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_token_exits_before_any_request(token: str | None) -> None:
    env = {key: value for key, value in os.environ.items() if key != "NEXUS_BROWSER_MCP_TOKEN"}
    if token is not None:
        env["NEXUS_BROWSER_MCP_TOKEN"] = token
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "tabs_list"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert "NEXUS_BROWSER_MCP_TOKEN" in result.stderr
    assert result.stdout == ""
