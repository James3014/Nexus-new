"""repo-learning: LocalFileBackend.append_learning_event / refresh_projection never
validate events against schemas/learning-event.v1.json and never re-derive
recommended_level from attempt evidence. A POST_EVIDENCE, AI_EXPLANATION,
ai_explanation_only, user_attempted=false event claiming L4 becomes L4 mastery,
and schema-forbidden extra fields (e.g. raw source excerpt) are persisted."""
import json, sys, tempfile
from pathlib import Path
REPO = Path("/home/user/repo-learning")
sys.path.insert(0, str(REPO / "src"))
import jsonschema
from repolearn.backends import LocalFileBackend
from repolearn.assessment import assess_judgment

schema = json.loads((REPO / "schemas/learning-event.v1.json").read_text())
event = {
    "schema": "repolearn.learning_event.v1", "event_id": "e1", "observed_at": "2026-10-01T00:00:00Z",
    "profile_id": "p1", "context": {}, "capability": {"domain": "security", "concept": "authz"},
    "attempt": {"cue_level": "HEAVY", "transfer_distance": "SAME_STRUCTURE", "judgment": "",
                "user_attempted": False, "ai_explanation_only": True,
                "evidence_timing": "POST_EVIDENCE", "evidence_provenance": "AI_EXPLANATION"},
    "assessment": {"classification": "EXPOSURE_ONLY", "recommended_level": "L4", "rationale": "x"},
    "source_excerpt": "def secret_internal(): PRIVATE_KEY='...'",   # not allowed by schema
}
try:
    jsonschema.validate(event, schema); print("schema: VALID")
except jsonschema.ValidationError as e:
    print("schema: INVALID ->", e.message[:100])
canon = assess_judgment(current_level=None, user_attempted=False, ai_explanation_only=True)
print("canonical assess_judgment recommended_level:", canon.recommended_level.value)
root = Path(tempfile.mkdtemp())
b = LocalFileBackend(root)
print("append:", b.append_learning_event("p1", event))
state = b.refresh_projection("p1")
print("projected concept level:", state["concepts"]["authz"]["level"], "domain level:", state["domains"]["security"]["level"])
print("excerpt persisted on disk:", "PRIVATE_KEY" in (root / "profiles/p1/events.jsonl").read_text())
