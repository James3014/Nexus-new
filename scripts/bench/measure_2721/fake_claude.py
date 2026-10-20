"""Zero-model stand-ins for the Claude CLI (dry runs, NEXUS_NOOP, tests).

``write_fake_claude(path, mode)`` writes an executable ``/usr/bin/python3``
script (a real file, not a symlink, as the measurement adapter requires).
It never calls a model.  Every run prints a stream-json ``system/init`` event
that carries ``fake_observed`` (argv, cwd, environment with the token value
masked) so a dry run can compare exactly what each arm launched, then a
successful ``result`` reporting ``claude-haiku-5-5``.

Modes:
* ``record``: no edit (the symmetry dry run);
* ``noop``: no edit (the NEXUS_NOOP arm: P1 with a worker that makes no
  model call must score 0 RESOLVED with an empty diff);
* ``edit``: appends one line to ``README.md`` (pipeline tests).
"""

from __future__ import annotations

import os
from pathlib import Path

FAKE_VERSION = "0.0.0 (Fake Claude, no model)"

_TEMPLATE = r'''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
MODE = "__MODE__"
args = sys.argv[1:]
if args == ["--version"]:
    print("__VERSION__")
    sys.exit(0)
env = {k: ("<set>" if k in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN") else v) for k, v in os.environ.items()}
import subprocess
try:
    status = subprocess.run(["/usr/bin/git", "status", "--porcelain", "--untracked-files=no"],
                            capture_output=True, text=True, timeout=20)
    git_status = {"rc": status.returncode, "out": status.stdout}
except Exception as exc:
    git_status = {"rc": None, "out": type(exc).__name__}
print(json.dumps({"type": "system", "subtype": "init", "model": "claude-haiku-5-5", "session_id": "fake",
                  "tools": ["Bash", "Edit", "Read", "Write"], "mcp_servers": [], "permissionMode": "acceptEdits",
                  "claude_code_version": "0.0.0",
                  "fake_observed": {"mode": MODE, "argv": args, "cwd": os.getcwd(), "env": env,
                                    "git_status": git_status}}))
if MODE == "edit" and not args[-1].startswith("Reply with exactly"):
    readme = Path("README.md")
    if readme.exists():
        readme.write_text(readme.read_text() + "\nfake edit\n")
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
                  "total_cost_usd": 0.0, "session_id": "fake",
                  "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0},
                  "modelUsage": {"claude-haiku-5-5": {"inputTokens": 0, "outputTokens": 0}}}))
'''


def write_fake_claude(path: Path, mode: str = "record") -> Path:
    if mode not in ("record", "noop", "edit"):
        raise ValueError(f"unknown fake mode {mode!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TEMPLATE.replace("__MODE__", mode).replace("__VERSION__", FAKE_VERSION), encoding="utf-8")
    path.chmod(0o755)
    return Path(os.path.realpath(path))
