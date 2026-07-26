#!/usr/bin/env python3
"""Run the Nexus governed self-hosted development MCP server over stdio."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer


if __name__ == "__main__":
    NexusSelfHostedMCPServer().serve(sys.stdin, sys.stdout)
