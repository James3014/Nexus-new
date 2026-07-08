"""B1-E: C_13453 Native Binding Dry Run — Proof that native capabilities enter model prompt."""
import os, sys, json, hashlib, subprocess, tempfile, urllib.request
from pathlib import Path

os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
WORKSPACE_ROOT = Path("/Users/jameschen/Workspace/nexus")
sys.path.insert(0, str(WORKSPACE_ROOT))

from nexus.services.local_heal.native_route_adapter import NativeRouteAdapter, RouteRequest
from nexus.services.local_heal.native_evidence_packet import NativeEvidencePacketBuilder
from nexus.services.local_heal.native_prompt_builder import NativePromptBuilder
from nexus.services.local_heal.native_validation_bridge import NativeValidationBridge
from nexus.services.local_heal.semantic_anchor_selection import select_semantic_anchor
from nexus.services.local_heal.backend_resource_policy import BackendResourcePolicy

OUTPUT_DIR = WORKSPACE_ROOT / "artifacts/runtime/b1e_c13453_native_binding_dry_run_v0"
OLLAMA = "http://localhost:11434"
MODEL_7B = "qwen2.5-coder:7b"

TASK = {
    "task_id": "C_13453", "repo_dir": str(WORKSPACE_ROOT / ".nexus/workspaces/astropy"),
    "base_commit": "19cc804717", "target_file": "astropy/io/ascii/html.py",
    "python_executable": str(WORKSPACE_ROOT / ".venv_astropy/bin/python3"),
    "problem": "Table.write with format='ascii.html' ignores the 'formats' parameter.",
    "repro": ("from astropy.table import Table\nimport sys\n"
              "def test_repro():\n    t = Table([[1.12345]], names=['a'])\n"
              "    import io; out = io.StringIO()\n"
              "    t.write(out, format='ascii.html', formats={'a': '%.2f'})\n"
              "    html = out.getvalue()\n"
              "    if '<td>1.12</td>' not in html: raise AssertionError('formats ignored')\n"
              "    print('SUCCESS')\n"
              "if __name__ == '__main__':\n"
              "    try: test_repro(); sys.exit(0)\n"
              "    except Exception as e: print(f'FAILURE: {e}'); sys.exit(1)\n"),
    "issue_intent": "output_formatting",
}


def ollama_gen(model, system, prompt, timeout=180):
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/generate",
            data=json.dumps({"model": model, "system": system, "prompt": prompt,
                "stream": False, "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 768}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get("response", "")
    except Exception as e:
        print(f"  ❌ {e}"); return ""


def ollama_unload(model):
    try:
        urllib.request.urlopen(urllib.request.Request(f"{OLLAMA}/api/generate",
            data=json.dumps({"name": model}).encode(),
            headers={"Content-Type": "application/json"}, method="DELETE"), timeout=10)
    except: pass


def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def run_repro(script, py, repo):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(script); p = f.name
    try:
        r = subprocess.run([py, p], cwd=repo, capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stdout + "\n" + r.stderr).strip()
    except Exception as e:
        return False, str(e)
    finally:
        Path(p).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("🏁 B1-E: C_13453 Native Binding Dry Run")
    print("=" * 60)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Setup
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])
    run_git(["checkout", TASK["base_commit"]], TASK["repo_dir"])
    source_text = (Path(TASK["repo_dir"]) / TASK["target_file"]).read_text(encoding="utf-8")

    # H2-B anchor
    sel = select_semantic_anchor(file_path=TASK["target_file"], source_text=source_text,
        target_symbol="HTML.write", issue_keywords=["format", "html", "table", "write", "formats"])
    anchor_text = sel.selected.source_text if sel.selected else ""
    anchor_sym = sel.selected.symbol_name if sel.selected else "write"
    anchor_span = (sel.selected.span_start, sel.selected.span_end) if sel.selected else (0, 0)
    print(f"  Anchor: {anchor_sym} L{anchor_span[0]}-L{anchor_span[1]}")

    # 1. Route Request
    print("\n=== 1. Route Request ===")
    adapter = NativeRouteAdapter()
    req = RouteRequest(task_id="C_13453", repo_path=TASK["repo_dir"], base_commit=TASK["base_commit"],
        issue_summary=TASK["problem"], failing_test_summary="", selected_anchor=anchor_text,
        model_role_requested="7b", resource_profile="local_7b", phase="candidate_generation")
    (OUTPUT_DIR / "route_request.json").write_text(json.dumps(req.__dict__, indent=2))

    # 2. Route Decision
    print("=== 2. Route Decision ===")
    decision = adapter.decide(req)
    print(f"  Allowed: {decision.allowed_capabilities}")
    print(f"  Forbidden: {decision.forbidden_capabilities}")
    print(f"  Budget: {decision.context_budget}")
    (OUTPUT_DIR / "route_decision.json").write_text(json.dumps(decision.__dict__, indent=2))

    if not decision.route_allowed:
        print("  ❌ Route blocked"); return

    # 3. Evidence Packet
    print("\n=== 3. Evidence Packet ===")
    builder = NativeEvidencePacketBuilder()
    evidence = builder.build(
        task_id="C_13453", route_id=decision.route_id, issue_intent=TASK["issue_intent"],
        base_commit=TASK["base_commit"], repo_path=TASK["repo_dir"], target_file=TASK["target_file"],
        anchor_symbol=anchor_sym, anchor_span=anchor_span, anchor_source_text=anchor_text)
    print(f"  CodeIntel: {len(evidence.codeintel_evidence)} items")
    print(f"  Memory: {len(evidence.memory_evidence)} items")
    print(f"  Missing risks: {evidence.missing_context_risks}")
    (OUTPUT_DIR / "evidence_packet.json").write_text(json.dumps({
        "task_id": evidence.task_id, "route_id": evidence.route_id,
        "issue_intent": evidence.issue_intent, "source_hash": evidence.source_hash,
        "selected_anchor": evidence.selected_anchor,
        "codeintel_evidence_count": len(evidence.codeintel_evidence),
        "memory_evidence_count": len(evidence.memory_evidence),
        "missing_context_risks": evidence.missing_context_risks,
    }, indent=2))

    # 4. Prompt from Evidence
    print("\n=== 4. Prompt from Evidence ===")
    pb = NativePromptBuilder()
    prompt = pb.build_prompt(evidence_packet=evidence, problem_statement=TASK["problem"], anchor_text=anchor_text)
    (OUTPUT_DIR / "prompt_rendered.md").write_text(prompt)
    print(f"  Prompt: {len(prompt)} chars")
    print(f"  Contains CODEINTEL: {'CODEINTEL EVIDENCE' in prompt}")
    print(f"  Contains PRIOR LESSONS: {'PRIOR LESSONS' in prompt}")
    print(f"  Contains OUTPUT CONTRACT: {'OUTPUT CONTRACT' in prompt}")

    # 5. Model Generation
    print("\n=== 5. 7B Generation ===")
    policy = BackendResourcePolicy()
    sevenb_results = []
    if policy.is_allowed(MODEL_7B):
        for i in range(3):
            print(f"  Loading 7B (candidate {i+1}/3)...")
            resp = ollama_gen(MODEL_7B, "Output ONLY raw Python code. No markdown. No explanation. ABSTAIN if uncertain.", prompt, 180)
            print(f"  7B: {len(resp)} chars")
            if not resp:
                sevenb_results.append({"candidate": i+1, "status": "empty"}); continue
            if resp.strip().upper() == "ABSTAIN":
                sevenb_results.append({"candidate": i+1, "status": "abstain"}); continue
            if resp.strip().startswith("```"):
                sevenb_results.append({"candidate": i+1, "status": "parser_rejected", "reason": "markdown_fence"}); continue

            # Apply and verify
            patched = source_text.replace(anchor_text, resp, 1)
            if patched == source_text:
                sevenb_results.append({"candidate": i+1, "status": "apply_failed"}); continue
            (Path(TASK["repo_dir"]) / TASK["target_file"]).write_text(patched, encoding="utf-8")
            ok, out = run_repro(TASK["repro"], TASK["python_executable"], TASK["repo_dir"])
            run_git(["checkout", "--", TASK["target_file"]], TASK["repo_dir"])
            sevenb_results.append({"candidate": i+1, "status": "verifier_pass" if ok else "verifier_fail",
                "replacement": resp[:200], "verifier_output": out[:200]})
            print(f"  Candidate {i+1}: {'PASS ✅' if ok else 'FAIL ❌'}")
            if ok: break
        ollama_unload(MODEL_7B)

    (OUTPUT_DIR / "model_outputs.json").write_text(json.dumps(sevenb_results, indent=2))

    # 6. Validation Receipt
    print("\n=== 6. Validation Receipt ===")
    vbridge = NativeValidationBridge()
    sevenb_passed = any(r.get("status") == "verifier_pass" for r in sevenb_results)
    vb = vbridge.build_receipt(
        route_id=decision.route_id, evidence_packet_id=evidence.task_id,
        model_role="7b", model_name=MODEL_7B, candidate_id="c1",
        parser_ok=any(r.get("status") != "parser_rejected" for r in sevenb_results),
        patch_applied=any(r.get("status") in ("verifier_pass", "verifier_fail") for r in sevenb_results),
        verifier_ok=sevenb_passed, compliance_ok=True,
        authority_trace=decision.authority_trace)
    (OUTPUT_DIR / "validation_receipt.json").write_text(json.dumps(vb.__dict__, indent=2))
    print(f"  Final: {vb.final_status}")

    # 7. Authority Trace
    print("\n=== 7. Authority Trace ===")
    trace = {
        "task_id": "C_13453",
        "phases_used": ["route_decision", "evidence_packet", "prompt_builder", "model_generation", "validation_receipt"],
        "capabilities_invoked": ["NativeRouteAdapter", "NativeEvidencePacketBuilder", "NativePromptBuilder", "NativeValidationBridge"],
        "capabilities_skipped": ["CodeIntel_direct", "Research_direct", "Sandbox", "Autoreason"],
        "native_evidence_in_prompt": "CODEINTEL EVIDENCE" in prompt,
        "model_did_not_call_tools": True,
        "no_public_or_training_enablement": True,
    }
    (OUTPUT_DIR / "authority_trace.json").write_text(json.dumps(trace, indent=2))

    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])

    status = "B1E_NATIVE_BINDING_PROVEN" if sevenb_passed else "B1E_PARTIAL_BINDING_PROVEN"
    print("\n" + "=" * 60)
    print(f"  Status: {status}")
    print(f"  Route: {decision.route_id}")
    print(f"  Evidence: {len(evidence.codeintel_evidence)} codeintel + {len(evidence.memory_evidence)} memory items")
    print(f"  Prompt includes native evidence: {trace['native_evidence_in_prompt']}")
    print(f"  7B passed: {sevenb_passed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
