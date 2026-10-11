"""Repro: effect_authorization.effects.filesystem.write_paths is validated as a
projection ceiling but never applied to the physical write guard. The worker's
mutation boundary comes from the prompt's authorized_mutation_paths instead."""
import sys, tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, "/home/user/nexus-open-swe-runtime")
from nexus_open_swe_runtime import cli
from deepagents.backends.filesystem import FilesystemBackend


class FakeGraph:
    def __init__(self, surface, output=None, effect=None):
        self.surface, self.output, self.effect = tuple(surface), output, effect
    def get_graph(self):
        tools = {n: object() for n in self.surface}
        return SimpleNamespace(nodes={"tools": SimpleNamespace(data=SimpleNamespace(tools_by_name=tools))})
    def invoke(self, _payload, config=None):
        if self.effect: self.effect()
        return self.output

def record(name, env):
    return {"messages": [SimpleNamespace(tool_calls=[{"name": name, "args": {"envelope": env}}])]}

tmp = Path(tempfile.mkdtemp())
ws = tmp / "workspace"; ws.mkdir()
(ws / "a.py").write_text("VALUE = 1\n"); (ws / "b.py").write_text("SECRET_GATE = True\n")
art = tmp / "evidence.json"; art.write_text('{"schema":"external_execution_envelope.v1","failure":"x"}\n')
req = {
    "schema": cli.REQUEST_SCHEMA, "operation": "worker_run", "operation_id": "b" * 64,
    "attempt_id": "attempt-1", "provider_id": "google_genai", "model_id": "m",
    "runtime_state_root": str(tmp / "state"), "workspace_path": str(ws), "artifact_path": str(art),
    # prompt widens mutation scope to b.py
    "prompt": "task_id=task-1\nunit_id=u1\nauthorized_mutation_paths=[\"b.py\"]\nbounded repair",
    "session_id": "", "worker_identity_sha256": "c" * 64,
}
auth = {
    "schema": "nexus.runtime.effect_authorization.v1", "authority_id": "owner", "authority_ref": "r",
    "operation_id": req["operation_id"], "attempt_id": req["attempt_id"],
    "repository": "James3014/other-repo", "source_revision": "1" * 40, "base_revision": "1" * 40,
    "workspace_id": "some-other-workspace", "target_id": "t", "expires_at": None,
    "effects": {"filesystem": {"write_paths": ["a.py"]}},   # ONLY a.py authorized
}
auth["authorization_hash"] = cli._sha256(cli._canonical_json(auth))
proj = {
    "schema": "nexus.runtime.tool_projection_manifest.v1", "authorization_hash": auth["authorization_hash"],
    "operation_id": req["operation_id"], "attempt_id": req["attempt_id"], "provider": "google_genai",
    "backend_id": "nexus-open-swe-runtime",
    "selected_tools": sorted(["read_file", "record_diagnosis", "record_worker_result", "write_file"]),
    "selected_effects": {"filesystem": {"write_paths": ["a.py"]}}, "authority_kind": "DERIVED_PROJECTION_ONLY",
}
proj["projection_hash"] = cli._sha256(cli._canonical_json(proj))
req["effect_authorization"], req["tool_projection_manifest"] = auth, proj

seen = {}
def repair_factory(model, workspace, runtime, allowed_paths, key, selected_tools=None):
    seen["allowed_paths"] = allowed_paths
    backend = cli.ScopedRepairBackend(FilesystemBackend(root_dir=workspace, virtual_mode=True), workspace, allowed_paths)
    def effect():
        backend.write("b.py", "SECRET_GATE = False\n")   # the production write guard
    return FakeGraph(("read_file", "record_worker_result", "write_file"), record("record_worker_result", {"summary": "done"}), effect)

diag = FakeGraph(("read_file", "record_diagnosis"), record("record_diagnosis", {"status": "ROOT_CAUSE_SUPPORTED", "summary": "s", "evidence_paths": ["b.py"]}))
res = cli._worker_run(req, runtime_loader=lambda: {"human_message": lambda content: content},
                      model_factory=lambda *a: object(), diagnosis_factory=lambda *a, **k: diag,
                      repair_factory=repair_factory)
print("status:", res["status"], "| tool_projection_status:", res.get("tool_projection_status"))
print("authorized write_paths:", auth["effects"]["filesystem"]["write_paths"])
print("allowed_paths handed to ScopedRepairBackend:", seen.get("allowed_paths"))
print("b.py now:", (ws / "b.py").read_text().strip())
print("receipt effect_authorization_hash present:", bool(res.get("effect_authorization_hash")))
