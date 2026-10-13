"""Repro: nexus/executors/cli_worker.py _validate_worker_argv forbidden-subcommand
denylist is bypassed by git global options (-C/-c) whose value token is not
skipped, and by un-listed destructive gh verbs. CliWorkerRequest is the sink
gate used by every worker/verifier spawn (run_cli_worker)."""
import sys, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.executors.cli_worker import CliWorkerRequest, _validate_worker_argv

cwd = tempfile.mkdtemp()
def try_argv(argv):
    try:
        _validate_worker_argv(argv)
        return "ACCEPTED"
    except ValueError as e:
        return f"REJECTED ({e})"

cases = [
    ("git", "push", "origin", "main"),                        # control
    ("git", "-C", ".", "push", "origin", "HEAD:main"),        # bypass
    ("git", "-c", "core.x=y", "push", "origin", "HEAD:main"), # bypass
    ("git", "-c", "a=b", "commit", "-m", "x"),                # bypass
    ("gh", "pr", "merge", "1"),                               # control
    ("gh", "-R", "o/r", "pr", "merge", "1"),                  # control (handled)
    ("gh", "repo", "delete", "o/r", "--yes"),                 # not listed
    ("gh", "release", "create", "v9"),                        # not listed
    ("gh", "workflow", "run", "x.yml"),                       # not listed
    ("gh", "secret", "set", "X"),                             # not listed
    ("git", "update-ref", "refs/heads/main", "deadbeef"),     # not listed
]
for argv in cases:
    print(" ".join(argv).ljust(55), try_argv(argv))

# End-to-end through the real sink dataclass (no process started):
req = CliWorkerRequest(executable="git", argv=("-C", ".", "push", "origin", "HEAD:refs/heads/main"), cwd=cwd)
print("CliWorkerRequest constructed for:", req.command[1:])
