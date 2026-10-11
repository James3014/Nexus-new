"""Repro: nexus/engine/cli_pregate.run_cli_pregate (called from
nexus/engine/pipeline_repair.py:1496 with commands from ctx.pack['verify_commands']
/ metadata) executes with shell=True and os.environ.copy(). It bypasses every
control the governed sink (CliWorkerRequest/run_cli_worker) applies: GitHub
credential env stripping, forbidden-subcommand denylist, shell-operator ban."""
import os, sys, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/Nexus-new")
os.environ["GH_TOKEN"] = "ghp_OWNERTOKEN_visible_to_verify_cmd"
from nexus.engine.cli_pregate import run_cli_pregate
from nexus.engine.target_env_context import TargetEnvContext
root = pathlib = tempfile.mkdtemp()
import pathlib
ctx = TargetEnvContext(engine_root=pathlib.Path(root), target_repo_root=pathlib.Path(root))
cmd = 'echo "GH_TOKEN=$GH_TOKEN"; echo would-run: git push origin HEAD:main && true'
ok, res = run_cli_pregate(ctx, [cmd], timeout_per_cmd=10)
print("passed:", ok); print(res[0]["stdout_tail"].strip())
# same command through the governed sink:
from nexus.orchestrator.candidate_verifier import CandidateVerifier
try:
    CandidateVerifier._build_verifier_request(cmd, root); print("governed sink: ACCEPTED")
except ValueError as e:
    print("governed sink: REJECTED ->", e)
