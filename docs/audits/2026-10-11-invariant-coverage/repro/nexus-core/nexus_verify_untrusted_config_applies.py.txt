"""Nexus Verify (MCP tool / `evidence-check`) reports VALID + APPLIES + VERIFIED for a
receipt produced from an untrusted worktree-only config with a no-op verifier, and for
an arbitrary repository_owner/name: config_source, subject_head and repo identity never
participate in the decision; integrity is only an unkeyed self-hash."""
import json, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/home/user/nexus-core")
from product.clients.local_golden_path import check_repository, init_repository
from product.clients.nexus_verify import evaluate_code_change_evidence_subject

def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
repo = Path(tempfile.mkdtemp()) / "r"; repo.mkdir()
git(repo, "init", "-q", "-b", "main"); git(repo, "config", "user.email", "a@b"); git(repo, "config", "user.name", "a")
(repo / "app.py").write_text("V = 0\n"); git(repo, "add", "-A"); git(repo, "commit", "-qm", "base")
git(repo, "checkout", "-qb", "f"); (repo / "app.py").write_text("V = 1\n"); git(repo, "commit", "-qam", "x")
# attacker-chosen, never-committed config whose verifier always passes
init_repository(repo, base_ref="main", verifier_command=(sys.executable, "-c", "pass"))
res = check_repository(repo)
receipt = json.loads(Path(res["receipt_path"]).read_text())
print("receipt config_source.kind =", receipt["config_source"]["kind"], "| verifier =", receipt["verifier"]["command"])
subject = {
    "repository_owner": "victim-org", "repository_name": "prod-service", "pr_number": 99,
    "current_base_sha": git(repo, "rev-parse", "main"), "current_head_sha": git(repo, "rev-parse", "HEAD"),
    "current_base_tree": git(repo, "rev-parse", "main^{tree}"), "current_head_tree": git(repo, "rev-parse", "HEAD^{tree}"),
    "changed_paths": ["app.py"], "deleted_paths": [],
}
out = evaluate_code_change_evidence_subject(subject, receipt)
print({k: out[k] for k in ("receipt_integrity", "evidence_applicability", "core_verification", "reason_codes")})

# Pure forgery: rewrite subject_head and config_source to look trusted, recompute the unkeyed self-hash.
from product.clients.local_golden_path import _receipt_hash, validate_verification_receipt_payload
receipt["config_source"] = {"kind": "base-ref", "ref": "main", "commit": "0"*40, "blob": "0"*40,
                            "worktree_config_hash": receipt["config_hash"], "config_drift": False}
receipt["subject_head"] = "git-commit:" + "1"*40
receipt["receipt_hash"] = _receipt_hash(receipt)
print("forged receipt validator:", validate_verification_receipt_payload(receipt))
