#!/usr/bin/env python3
"""Probe whether an MCP host offers form elicitation the Owner can trust (#1750).

Register this file as a stdio MCP server in a host (Claude Code, Claude
Desktop, or any other client), ask the agent to call ``nexus_elicitation_probe``
and answer the dialog yourself.  The server records, outside the model's
reach, what the host declared at ``initialize`` and what it returned for the
elicitation request.  Results are appended as JSON lines to the path given as
the first argument (default: ./mcp-elicitation-probe.jsonl).

The probe grants nothing and touches no Nexus state.
"""

from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any

SUPPORTED_VERSIONS = ("2025-06-18", "2025-11-25")


def _write(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    log_path = Path(argv[1] if len(argv) > 1 else "mcp-elicitation-probe.jsonl")
    record: dict[str, Any] = {"started_at": time.time()}
    pending_call: Any = None
    probe_id = ""

    def append(entry: dict[str, Any]) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        method = message.get("method")
        if method == "initialize":
            params = message.get("params") or {}
            requested = str(params.get("protocolVersion") or "")
            record.update(
                client_info=params.get("clientInfo"),
                requested_protocol=requested,
                capabilities=params.get("capabilities"),
            )
            append({"event": "initialize", **record})
            _write({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "protocolVersion": requested
                    if requested in SUPPORTED_VERSIONS
                    else "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "nexus-elicitation-probe", "version": "1"},
                },
            })
        elif method == "tools/list":
            _write({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "tools": [
                        {
                            "name": "nexus_elicitation_probe",
                            "description": "Ask the human to answer a test confirmation dialog. Grants nothing.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": False,
                            },
                        }
                    ]
                },
            })
        elif method == "tools/call":
            pending_call = message["id"]
            probe_id = f"probe-{secrets.token_hex(8)}"
            append({"event": "elicitation_sent", "request_id": probe_id, "sent_at": time.time()})
            _write({
                "jsonrpc": "2.0",
                "id": probe_id,
                "method": "elicitation/create",
                "params": {
                    "message": f"Nexus elicitation probe {probe_id[-8:]}. This grants nothing. "
                    "Accept and tick the box only if you, a human, are answering.",
                    "requestedSchema": {
                        "type": "object",
                        "properties": {
                            "approve": {"type": "boolean", "title": "I am the human Owner"}
                        },
                        "required": ["approve"],
                    },
                },
            })
        elif method is None and message.get("id") == probe_id and pending_call is not None:
            append({
                "event": "elicitation_answer",
                "request_id": probe_id,
                "answer": message,
                "answered_at": time.time(),
            })
            _write({
                "jsonrpc": "2.0",
                "id": pending_call,
                "result": {
                    "content": [
                        {"type": "text", "text": "Probe answer recorded in " + str(log_path)}
                    ]
                },
            })
            pending_call = None
        elif method == "ping" and "id" in message:
            _write({"jsonrpc": "2.0", "id": message["id"], "result": {}})
        elif "id" in message and method is not None:
            _write({
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32601, "message": "not supported"},
            })
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
