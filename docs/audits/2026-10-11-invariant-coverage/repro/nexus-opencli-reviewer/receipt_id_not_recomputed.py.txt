"""nexus-opencli-reviewer: publish_review (sink of `reviewer.cli --publish-receipt FILE`)
never recomputes receipt_id = sha256(identity, context, prompt, raw_response_sha256).
A semantic result produced for PR 7 can be re-targeted to PR 8's *current* identity
(and its semantic_result edited) while keeping the original receipt_id; the fresh-identity
rebind passes because it only compares the (substituted) identity with GitHub."""
import hashlib, json, sys, tempfile
sys.path.insert(0, "/home/user/nexus-opencli-reviewer")
from reviewer.publication import publish_review

def rid(identity, ctx, prompt, raw):
    return hashlib.sha256(json.dumps({"identity": identity, "context": ctx, "prompt": prompt, "raw": raw},
                          sort_keys=True, separators=(",", ":")).encode()).hexdigest()

ident7 = ["o/r", 7, "h7", "b", "m"]
raw_sha = hashlib.sha256(b'{"status":"FINDINGS"}').hexdigest()
genuine = {"schema": "reviewer.pre_review.v1", "review_identity": ident7, "claim_ceiling": "PRE_REVIEW_ONLY",
           "context_pack_sha256": "c7", "prompt_sha256": "p7", "raw_response_sha256": raw_sha,
           "outcome_unknown": False, "retry_safe": False, "transport_result": "REVIEW_COMPLETED",
           "parse_result": "PARSED",
           "semantic_result": {"schema": "reviewer.semantic_response.v1", "status": "FINDINGS",
                               "summary": "real findings for PR7", "findings": [], "evidence_gaps": []}}
genuine["receipt_id"] = rid(ident7, "c7", "p7", raw_sha)

forged = json.loads(json.dumps(genuine))
forged["review_identity"] = ["o/r", 8, "h8", "b", "m"]      # substituted review identity
forged["semantic_result"]["status"] = "PASS"                  # edited semantic verdict
forged["semantic_result"]["summary"] = "LGTM, no issues"
print("receipt_id still claims:", forged["receipt_id"][:16],
      "recomputed for forged content:", rid(forged["review_identity"], "c7", "p7", raw_sha)[:16])

class GH:
    comments = []
    def get_authenticated_login(self): return "sidecar"
    def get_pr(self, repo, n): return {"head": {"sha": f"h{n}"}, "base": {"sha": "b"}}
    def get_ref(self, repo, br): return {"object": {"sha": "m"}}
    def list_comments(self, repo, n): return [c for c in self.comments if c["pr"] == n]
    def create_comment(self, repo, n, body):
        c = {"id": 1, "pr": n, "body": body, "html_url": "u", "user": {"login": "sidecar"}}
        self.comments.append(c); return c

gh = GH()
path = publish_review(tempfile.mkdtemp(), gh, forged)
print("PUBLISHED:", json.loads(open(path).read())["state"], "to PR", gh.comments[0]["pr"])
print("body excerpt:", [l for l in gh.comments[0]["body"].splitlines() if "LGTM" in l or "PASS" in l][:2])
