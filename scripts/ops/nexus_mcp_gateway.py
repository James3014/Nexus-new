#!/usr/bin/env python3
"""Run the single public Nexus MCP gateway over stdio."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single Nexus MCP gateway")
    parser.add_argument("--self-test", action="store_true", help="run a protocol-only smoke check")
    args = parser.parse_args(argv)
    gateway = UnifiedMCPGateway()
    if args.self_test:
        response = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        if not response or len(response["result"]["tools"]) != 9:
            raise SystemExit("gateway self-test failed")
        print("nexus-mcp-gateway self-test: PASS")
        return 0
    gateway.serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
