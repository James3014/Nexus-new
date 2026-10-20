"""Zero-model stand-ins for the Claude CLI (dry runs, NEXUS_NOOP, tests).

``write_fake_claude(path, mode)`` writes an executable ``/usr/bin/python3``
script (a real file, not a symlink, as the measurement adapter requires).
It never calls a model.  Every run prints a stream-json ``system/init`` event
that carries ``fake_observed`` (argv, cwd, environment with the token value
masked) so a dry run can compare exactly what each arm launched, then a
successful ``result``.  A row run reports its own model label
``fake-<mode>`` (init and modelUsage), never a real model name, so a fake
run can never pass for the measured model.  Only the adapter's readiness
probe (never a row) names the measured model, or P1 would refuse the worker.

Modes:
* ``record``: no edit (the symmetry dry run);
* ``noop``: no edit (the NEXUS_NOOP arm: P1 with a worker that makes no
  model call must score 0 RESOLVED with an empty diff);
* ``edit``: appends one line to ``README.md`` (pipeline tests);
* ``venvprobe``: runs ``python -c 'import encodings'`` and a pytest
  collection with the task venv inside the sandbox, reported as a
  ``system/venv_probe`` event;
* ``tmpprobe``: reports the sandboxed temp dir and runs a pytest with ``tmp_path``,
  listing any ``pytest-*`` dir left in the cwd (``system/tmp_probe``);
* ``smoke``: edits ``README.md`` (outside the allowed scope) and creates an
  untracked file in the first allowed directory;
* ``hang``: writes one file, then sleeps past any time cap (timeout snapshot).
"""

from __future__ import annotations

import os
from pathlib import Path

FAKE_VERSION = "0.0.0 (Fake Claude, no model)"
FAKE_MODEL_PREFIX = "fake-"

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
probe_run = not args[-1].startswith("Reply with exactly")
# Row runs carry only the fake label.  The one exception is the adapter's own
# readiness probe (not a row: its trace is filed under the probe task id), which
# P1 refuses unless it names the measured model; without it NEXUS_NOOP could not
# reach the worker at all.
FAKE_MODEL = ("fake-" + MODE) if probe_run else "claude-haiku-5-5"
print(json.dumps({"type": "system", "subtype": "init", "model": FAKE_MODEL, "session_id": "fake",
                  "tools": ["Bash", "Edit", "Read", "Write"], "mcp_servers": [], "permissionMode": "acceptEdits",
                  "claude_code_version": "0.0.0",
                  "fake_observed": {"mode": MODE, "argv": args, "cwd": os.getcwd(), "env": env,
                                    "git_status": git_status}}))
venv_probe = {}
if MODE == "venvprobe" and probe_run:
    # The task venv must work inside the sandbox in both arms.
    for name, cmd in (("import_encodings", ["python", "-c", "import encodings, sys; print(sys.prefix)"]),
                      ("pytest_collect", ["python", "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"])):
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            venv_probe[name] = {"rc": done.returncode, "tail": (done.stdout + done.stderr)[-400:]}
        except Exception as exc:
            venv_probe[name] = {"rc": None, "tail": type(exc).__name__}
    print(json.dumps({"type": "system", "subtype": "venv_probe", "venv_probe": venv_probe}))
if MODE == "tmpprobe" and probe_run:
    # Where a test run's temp files land inside the worker sandbox (35, M-main2): the
    # temp dir Python resolves, and whether pytest leaves its basetemp in the cwd.
    import tempfile
    probe = {"TMPDIR": os.environ.get("TMPDIR"), "CLAUDE_CODE_TMPDIR": os.environ.get("CLAUDE_CODE_TMPDIR"),
             "gettempdir": tempfile.gettempdir(), "cwd": os.getcwd()}
    def _writable(directory):
        try:
            fd, path = tempfile.mkstemp(dir=directory, prefix=".m2721-w-")
            os.close(fd)
            os.unlink(path)
            return True
        except Exception:
            return False
    probe["writable"] = {name: _writable(path) for name, path in (
        ("TMPDIR", os.environ.get("TMPDIR") or ""), ("/tmp", "/tmp"), ("/var/tmp", "/var/tmp"),
        ("cwd", os.getcwd())) if path}
    test_dir = Path(tempfile.mkdtemp(prefix="m2721-tmpprobe-"))
    (test_dir / "test_tmpprobe.py").write_text("def test_tmp(tmp_path):\n    (tmp_path / 'f').write_text('x')\n")
    done = subprocess.run(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test_dir)],
                          capture_output=True, text=True, timeout=300)
    probe["pytest_rc"] = done.returncode
    probe["pytest_tail"] = (done.stdout + done.stderr)[-600:]
    probe["cwd_pytest_dirs"] = sorted(p.name for p in Path.cwd().iterdir() if p.name.startswith("pytest-"))
    print(json.dumps({"type": "system", "subtype": "tmp_probe", "tmp_probe": probe}))
if MODE in ("edit", "smoke") and probe_run:
    readme = Path("README.md")
    if readme.exists():
        readme.write_text(readme.read_text() + "\nfake edit\n")
if MODE == "smoke" and probe_run:
    # Smoke shapes the measurement must handle: an untracked new file inside the
    # first allowed directory and an edit outside the allowed scope (README above).
    allowed = next((line.split(":", 1)[1] for line in args[-1].splitlines() if line.startswith("Allowed files:")), "")
    scope = next((entry.strip() for entry in allowed.split(",") if entry.strip().endswith("/")), "")
    if scope and Path(scope).is_dir():
        (Path(scope) / "m2721_smoke_new_file.py").write_text("SMOKE = 1\n")
if MODE == "hang" and probe_run:
    import time
    Path("hang_started.txt").write_text("worker edit before the cap\n")
    time.sleep(10 ** 6)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
                  "total_cost_usd": 0.0, "session_id": "fake",
                  "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0},
                  "modelUsage": {FAKE_MODEL: {"inputTokens": 0, "outputTokens": 0}}}))
'''


def write_fake_claude(path: Path, mode: str = "record") -> Path:
    if mode not in ("record", "noop", "edit", "venvprobe", "tmpprobe", "smoke", "hang"):
        raise ValueError(f"unknown fake mode {mode!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TEMPLATE.replace("__MODE__", mode).replace("__VERSION__", FAKE_VERSION), encoding="utf-8")
    path.chmod(0o755)
    return Path(os.path.realpath(path))
