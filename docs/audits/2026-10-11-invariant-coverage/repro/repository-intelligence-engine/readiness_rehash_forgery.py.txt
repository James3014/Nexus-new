"""RIE: readiness disposition / is_review_ready can be forged and re-hashed;
verify_cloud_bundle and verify_repository_intelligence_report both accept it,
unlike the CFI verifier which rejects re-hashed semantic changes."""
import copy, sys
REPO = "/home/user/repository-intelligence-engine"
sys.path.insert(0, REPO); sys.path.insert(0, REPO + "/tests")
from adapters import github_action as gha
from test_github_action import FakeGitHubAPI
from repository_intelligence import core as ri
from repository_intelligence.models import CheckObservation, PRSnapshot

class StaleBaseAPI(FakeGitHubAPI):
    def get_json(self, path, params=None):
        if path == "/repos/owner/repo/git/ref/heads/main":
            return {"object": {"sha": "c" * 40}}   # main moved -> base is stale
        return super().get_json(path, params)

snap = gha.collect_pr_snapshot(StaleBaseAPI(), "owner/repo", 7)
bundle = gha.run_cloud_bundle(snap)
r = bundle["reports"]["readiness"]["result"]
print("genuine readiness:", r["disposition"], "is_review_ready=", r["is_review_ready"],
      "stale_base=", r["identity"]["stale_base"], "eia=", bundle["reports"]["eia"]["result"]["decision"])
print("genuine verify_cloud_bundle:", gha.verify_cloud_bundle(bundle))
t = copy.deepcopy(bundle)
t["reports"]["readiness"]["result"].update(disposition="REVIEW_READY", is_review_ready=True,
                                           findings=[], reasons=[], evidence_gaps=[], risk="LOW")
t["content_sha256"] = gha._hash_payload(t)
print("forged readiness REVIEW_READY (stale_base still True) verify_cloud_bundle:", gha.verify_cloud_bundle(t))

# Same for the repository report verifier
pr = PRSnapshot(repository="owner/repo", pr_number=1, title="t", state="open", draft=True, mergeable=True,
                base_branch="main", base_sha="base1", head_branch="f", head_sha="head1",
                current_main_sha="main2", changed_files=("a.py",), checks=(CheckObservation(name="ci", status="success"),))
p = ri.build_repository_intelligence_report([pr]).to_dict()
print("genuine item:", p["items"][0]["disposition"], p["items"][0]["is_review_ready"], "is_valid=", p["items"][0]["identity"]["is_valid"])
p["items"][0].update(disposition="REVIEW_READY", is_review_ready=True)
p["items"][0]["identity"]["is_valid"] = False   # incoherent: invalid identity yet ready
p["content_sha256"] = ri._content_hash(p)
print("forged item verify_repository_intelligence_report:", ri.verify_repository_intelligence_report(p))
