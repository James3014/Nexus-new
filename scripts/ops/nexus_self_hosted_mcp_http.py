#!/usr/bin/env python3
"""Run the Nexus governed self-hosted development MCP server over authenticated HTTP."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.orchestrator.self_hosted_mcp_http import MCPHTTPConfigError, serve_from_env  # noqa: E402


def main() -> int:
    try:
        serve_from_env(expected_repo_root=REPO_ROOT)
    except MCPHTTPConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
