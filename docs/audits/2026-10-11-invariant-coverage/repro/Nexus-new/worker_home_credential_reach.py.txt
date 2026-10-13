"""Repro: run_cli_worker strips GitHub credential ENV keys but inherits the
ambient HOME (allowlist), so a worker/verifier process can read gh's stored
OAuth token ($HOME/.config/gh/hosts.yml) or git credential store. The
'no GitHub credential in worker namespace' invariant is env-only."""
import os, sys, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/Nexus-new")
fake_home = tempfile.mkdtemp()
os.makedirs(f"{fake_home}/.config/gh")
open(f"{fake_home}/.config/gh/hosts.yml", "w").write("github.com:\n    oauth_token: " + "gho" + "_FAKEOWNERTOKEN0000000000000000\n")
open(f"{fake_home}/.git-credentials", "w").write("https://owner:ghp_FAKE000000000000000000000000@github.com\n")
os.environ["HOME"] = fake_home          # simulate the Owner's real HOME
os.environ["GH_TOKEN"] = "ghp_should_be_stripped"
from nexus.executors.cli_worker import CliWorkerRequest, run_cli_worker
code = ("import os;h=os.environ['HOME'];"
        "print('GH_TOKEN in env:', 'GH_TOKEN' in os.environ);"
        "print(open(h+'/.config/gh/hosts.yml').read().strip());"
        "print(open(h+'/.git-credentials').read().strip())")
res = run_cli_worker(CliWorkerRequest(executable=sys.executable, argv=("-c", code), cwd=tempfile.mkdtemp()))
print(res.status.value, res.exit_code); print(res.stdout.decode())
