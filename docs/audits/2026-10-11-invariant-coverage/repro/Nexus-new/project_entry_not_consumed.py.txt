"""Repro (static, runs against real source): AGENTS.md #842 says the coordinator
MUST call nexus_project_entry before any governed effect and that switching
repo/Issue invalidates the prior binding. The gateway emits project_binding_hash
but no effectful handler (task_card_create/commit, standing grant issue,
worker_candidate, candidate_* , task_finish) reads any project-entry binding,
and _project_entry persists nothing, so there is no binding to invalidate."""
import ast, pathlib, re
root = pathlib.Path("/home/user/Nexus-new")
src = (root / "nexus/orchestrator/unified_mcp_gateway.py").read_text()
tree = ast.parse(src)
effectful = {"_task_card_create","_task_card_commit","_owner_standing_grant_issue","_worker_candidate",
             "_candidate_approve","_candidate_integrate","_candidate_bind_integration","_candidate_adopt_external",
             "_finish","_task_run","_assist_submit","_mutation_admit"}
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in effectful:
        body = ast.get_source_segment(src, node)
        hit = bool(re.search(r"project_entry|project_binding", body))
        print(f"{node.name:32} references project entry binding: {hit}")
pe = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_project_entry")
seg = ast.get_source_segment(src, pe)
print("_project_entry persists state (self.<attr> = / write):", bool(re.search(r"self\.\w+\s*=|_write|write_text", seg)))
readers = [str(p.relative_to(root)) for p in (root/"nexus").rglob("*.py")
           if "project_binding_hash" in p.read_text(errors="ignore")]
print("files mentioning project_binding_hash:", readers)
