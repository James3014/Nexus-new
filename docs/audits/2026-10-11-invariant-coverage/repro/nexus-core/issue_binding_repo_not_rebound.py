"""check_issue trusts github_repository from the caller-writable binding file
(.nexus-core/issues/N.json, unkeyed self-hash) and never re-compares it with the
repository's origin (init_issue_binding does). A forged binding pointing at an
attacker-controlled repo's Issue #N yields Issue VERIFIED, and receipt-check
--expect-issue N passes unless --expect-github-repository is also given."""
import json, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, "/home/user/nexus-core")
from product.clients import issue_golden_path as igp
from product.protocol.generic_verification import canonical_hash
from product.clients.local_golden_path import _load_effective_config
from product.clients.cli import main as cli

PY = sys.executable
def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
repo = Path(tempfile.mkdtemp()) / "r"; repo.mkdir()
git(repo, "init", "-q", "-b", "main"); git(repo, "config", "user.email", "a@b"); git(repo, "config", "user.name", "a")
git(repo, "remote", "add", "origin", "https://github.com/James3014/nexus-core.git")
(repo / ".nexus-core").mkdir()
(repo / ".nexus-core/config.toml").write_text(
    f'version = 1\nbase_ref = "main"\nallowed_patterns = ["**"]\ndeletion_policy = "FORBID"\n'
    f'verifier_command = {json.dumps([PY, "-c", "pass"])}\ntimeout_seconds = 60\n')
(repo / ".gitignore").write_text(".nexus-core/issues/\n.nexus-core/receipts/\n")
(repo / "app.py").write_text("V = 0\n"); git(repo, "add", "-A"); git(repo, "commit", "-qm", "base")
git(repo, "checkout", "-qb", "f"); (repo / "app.py").write_text("V = 1\n"); git(repo, "commit", "-qam", "x")

cfg_hash = canonical_hash(_load_effective_config(repo)[0])
EVIL = "attacker/elsewhere"
raw = {"number": 7, "title": "anything", "state": "open",
       "body": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {cfg_hash} -->", "author_association": "OWNER",
       "user": {"login": "attacker"}}
def reader(github_repo, n):           # stands in for GitHub; attacker owns EVIL/#7
    assert github_repo == EVIL, github_repo
    return raw

# Sanity: the official init path rejects the mismatch with origin
try:
    igp.init_issue_binding(repo, issue_number=7, github_repo=EVIL, issue_reader=reader)
except igp.LocalCheckError as e:
    print("issue-init --github-repo attacker/elsewhere ->", e.reason_code)

# Forge binding by hand (unkeyed self-hash is recomputable)
contract = igp._issue_contract(EVIL, 7, raw); h = canonical_hash(contract)
payload = {"schema": igp.ISSUE_BINDING_SCHEMA, "version": 2, "bound_at": datetime.now(timezone.utc).isoformat(),
           "github_repository": EVIL, "issue_number": 7, "issue_contract": contract, "issue_contract_hash": h,
           "github_updated_at": None,
           "evidence_sufficiency": {"schema": igp.ISSUE_EVIDENCE_SUFFICIENCY_SCHEMA,
                                    "config_path": ".nexus-core/config.toml", "config_hash": cfg_hash,
                                    "source": "issue-contract-marker", "issue_contract_hash": h},
           "binding_hash": None}
payload["binding_hash"] = igp._hash_without_binding(payload)
(repo / ".nexus-core/issues").mkdir(); (repo / ".nexus-core/issues/7.json").write_text(json.dumps(payload))

res = igp.check_issue(repo, issue_number=7, issue_reader=reader, require_trusted_config=True)
print("issue-check:", res["status"], res["github_repository"], res["claim_ceiling"])
base = ["receipt-check", "--receipt", str(res["receipt_path"]), "--expect-status", "VERIFIED", "--expect-issue", "7",
        "--require-trusted-config", "--require-clean-subject"]
print("receipt-check --expect-issue 7 exit:", cli(base))
print("receipt-check ... --expect-github-repository James3014/nexus-core exit:",
      cli(base + ["--expect-github-repository", "James3014/nexus-core"]))
