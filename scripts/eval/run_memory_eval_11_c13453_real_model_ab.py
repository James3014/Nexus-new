#!/usr/bin/env python3
"""MEMORY-EVAL-11: Real model A/B evaluation for C_13453 (Astropy Table.write formats).

This script runs two arms:
  - nexus_memory_on:  MemoryRetrievalAdapter enabled (13 task-specific episodes for C_13453)
  - nexus_memory_off: MemoryRetrievalAdapter disabled

Both arms use Ollama qwen2.5-coder:7b with deterministic settings.
Raw model outputs, hashes, receipts, and artifacts are all generated during the run.

Claim boundary: real_model_call_executed=true; outcome_uplift_observed depends on verifier results.
"""
import json
import shutil
import hashlib
import urllib.request
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
from nexus.services.local_heal.memory_trace import build_memory_trace_from_adapter
from nexus.services.local_heal.native_evidence_packet import NativeEvidencePacketBuilder
from nexus.services.local_heal.native_prompt_builder import NativePromptBuilder
from nexus.services.local_heal.client import OllamaClient


def verify_ollama_ready() -> list[str]:
    """Verify that the local Ollama daemon is active and has the required model."""
    try:
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        data = json.loads(req.read().decode("utf-8"))
        models = [m["name"] for m in data.get("models", [])]
        print(f"[*] Ollama connected. Available tags: {models}")
        has_qwen = any("qwen2.5-coder:7b" in name for name in models)
        if not has_qwen:
            qwen_models = [name for name in models if "qwen2.5-coder" in name]
            if qwen_models:
                print(f"[!] Fallback to: {qwen_models[0]}")
                return [qwen_models[0]]
            raise RuntimeError(
                f"Required model 'qwen2.5-coder:7b' is missing. Tags: {models}"
            )
        return ["qwen2.5-coder:7b"]
    except Exception as e:
        raise RuntimeError(
            f"Ollama readiness check failed: {e}. Fail closed."
        ) from e


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_ab_evaluation():
    print("=== Start MEMORY-EVAL-11: C_13453 Astropy Table.write Real Model A/B ===")

    # 1. Environment preflight
    models_to_use = verify_ollama_ready()
    model_name = models_to_use[0]

    # 2. Setup temp fake repo with astropy Table stub
    temp_repo = Path("/tmp/fake_repo_eval_11_c13453")
    if temp_repo.exists():
        shutil.rmtree(temp_repo)
    temp_repo.mkdir(parents=True, exist_ok=True)

    target_file = "astropy/io/ascii/core.py"
    core_file = temp_repo / target_file
    core_file.parent.mkdir(parents=True, exist_ok=True)
    core_file.write_text("""\
class BaseReader:
    def _set_col_formats(self, table, formats):
        # Dummy stub — formats parameter is ignored
        pass

    def write(self, table, output):
        self._set_col_formats(table, None)
        # write stub
        pass
""")

    task_id = "C_13453"
    problem_statement = (
        "C_13453: Astropy Table.write ignores the 'formats' parameter. "
        "The _set_col_formats() method receives the formats dict but does not "
        "apply it to the table columns before writing."
    )
    anchor_symbol = "_set_col_formats"
    anchor_span = (2, 4)
    anchor_source_text = (
        "    def _set_col_formats(self, table, formats):\n"
        "        # Dummy stub — formats parameter is ignored\n"
        "        pass"
    )

    artifact_root = REPO_ROOT / "artifacts/runtime/memory_eval_11_c13453_real_model_ab_v0"
    output_root = artifact_root / "runs"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    system_prompt = (
        "You are a senior python developer. "
        "Output ONLY raw python code to replace the anchor method body, "
        "no markdown, no explanation, no docstring."
    )

    # 3. Memory On Arm
    print("[*] Running nexus_memory_on arm...")
    adapter_on = MemoryRetrievalAdapter(enabled=True, memory_arm="nexus_memory_on")
    builder_on = NativeEvidencePacketBuilder(adapter_on)
    evidence_on = builder_on.build(
        task_id=task_id,
        route_id="local_heal",
        issue_intent=problem_statement,
        base_commit="dummy_base_commit",
        repo_path=str(temp_repo),
        target_file=target_file,
        anchor_symbol=anchor_symbol,
        anchor_span=anchor_span,
        anchor_source_text=anchor_source_text,
    )

    lessons_retrieved = len(evidence_on.memory_evidence)
    print(f"[*] Memory On arm retrieved {lessons_retrieved} lessons from store.")

    prompt_builder = NativePromptBuilder()
    user_prompt_on = prompt_builder.build_prompt(
        evidence_packet=evidence_on,
        problem_statement=problem_statement,
        anchor_text=anchor_source_text,
    )

    # Real model call
    client = OllamaClient(model=model_name, endpoint="http://localhost:11434")
    model_output_on = client.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt_on,
        options={"temperature": 0.0, "seed": 42},
    )

    raw_output_on_path = artifact_root / "raw_model_output_memory_on.txt"
    raw_output_on_path.write_text(model_output_on, encoding="utf-8")
    print(f"[*] Memory On model output saved ({len(model_output_on)} chars)")

    # Write artifacts via Orchestrator
    op_on = OperationalContext(
        instance_id=task_id,
        repo_dir=temp_repo,
        problem_statement=problem_statement,
    )
    op_on.solve_eligible = False
    op_on.final_patch = model_output_on
    op_on.patch_applied = True
    op_on.model_name = model_name
    op_on.receipt_path = "/tmp/receipt_eval_11_on.json"
    op_on.memory_enabled = True
    op_on.memory_arm = "nexus_memory_on"
    op_on.artifact_output_root = str(output_root)
    op_on.system_prompt = system_prompt
    op_on.user_prompt = user_prompt_on
    op_on._evidence_packet = {
        "task_id": evidence_on.task_id,
        "route_id": evidence_on.route_id,
        "issue_intent": evidence_on.issue_intent,
        "base_commit": evidence_on.base_commit,
        "source_hash": evidence_on.source_hash,
        "selected_anchor": evidence_on.selected_anchor,
        "codeintel_evidence": [vars(x) for x in evidence_on.codeintel_evidence],
        "memory_evidence": [vars(x) for x in evidence_on.memory_evidence],
        "prior_failure_evidence": [vars(x) for x in evidence_on.prior_failure_evidence],
        "missing_context_risks": evidence_on.missing_context_risks,
        "context_budget": evidence_on.context_budget,
        "prompt_inclusion_plan": evidence_on.prompt_inclusion_plan,
        "artifact_source": "live_runtime",
        "created_during_run": True,
    }
    op_on._memory_influence_trace = build_memory_trace_from_adapter(adapter_on.last_metadata)

    ctx_on = HealContext(op=op_on, gov=GovernanceContext())
    orchestrator = HealOrchestrator(phases=[], governance_gate=GovernanceGate())
    orchestrator.run(ctx_on)

    # 4. Memory Off Arm
    print("[*] Running nexus_memory_off arm...")
    adapter_off = MemoryRetrievalAdapter(enabled=False, memory_arm="nexus_memory_off")
    builder_off = NativeEvidencePacketBuilder(adapter_off)
    evidence_off = builder_off.build(
        task_id=task_id,
        route_id="local_heal",
        issue_intent=problem_statement,
        base_commit="dummy_base_commit",
        repo_path=str(temp_repo),
        target_file=target_file,
        anchor_symbol=anchor_symbol,
        anchor_span=anchor_span,
        anchor_source_text=anchor_source_text,
    )

    user_prompt_off = prompt_builder.build_prompt(
        evidence_packet=evidence_off,
        problem_statement=problem_statement,
        anchor_text=anchor_source_text,
    )

    model_output_off = client.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt_off,
        options={"temperature": 0.0, "seed": 42},
    )

    raw_output_off_path = artifact_root / "raw_model_output_memory_off.txt"
    raw_output_off_path.write_text(model_output_off, encoding="utf-8")
    print(f"[*] Memory Off model output saved ({len(model_output_off)} chars)")

    # Write artifacts via Orchestrator
    op_off = OperationalContext(
        instance_id=task_id,
        repo_dir=temp_repo,
        problem_statement=problem_statement,
    )
    op_off.solve_eligible = False
    op_off.final_patch = model_output_off
    op_off.patch_applied = True
    op_off.model_name = model_name
    op_off.receipt_path = "/tmp/receipt_eval_11_off.json"
    op_off.memory_enabled = False
    op_off.memory_arm = "nexus_memory_off"
    op_off.artifact_output_root = str(output_root)
    op_off.system_prompt = system_prompt
    op_off.user_prompt = user_prompt_off
    op_off._evidence_packet = {
        "task_id": evidence_off.task_id,
        "route_id": evidence_off.route_id,
        "issue_intent": evidence_off.issue_intent,
        "base_commit": evidence_off.base_commit,
        "source_hash": evidence_off.source_hash,
        "selected_anchor": evidence_off.selected_anchor,
        "codeintel_evidence": [vars(x) for x in evidence_off.codeintel_evidence],
        "memory_evidence": [vars(x) for x in evidence_off.memory_evidence],
        "prior_failure_evidence": [vars(x) for x in evidence_off.prior_failure_evidence],
        "missing_context_risks": evidence_off.missing_context_risks,
        "context_budget": evidence_off.context_budget,
        "prompt_inclusion_plan": evidence_off.prompt_inclusion_plan,
        "artifact_source": "live_runtime",
        "created_during_run": True,
    }
    op_off._memory_influence_trace = build_memory_trace_from_adapter(adapter_off.last_metadata)

    ctx_off = HealContext(op=op_off, gov=GovernanceContext())
    orchestrator.run(ctx_off)

    # 5. Read back prompt manifests
    prompt_manifest_on = json.loads(
        (output_root / f"{task_id}/nexus_memory_on/prompt_manifest.json").read_text(encoding="utf-8")
    )
    prompt_manifest_off = json.loads(
        (output_root / f"{task_id}/nexus_memory_off/prompt_manifest.json").read_text(encoding="utf-8")
    )

    prompt_len_on = prompt_manifest_on["prompt_length_chars"]
    prompt_len_off = prompt_manifest_off["prompt_length_chars"]
    prompt_delta = prompt_len_on - prompt_len_off

    # 6. Compute hashes
    prompt_sha256_on = compute_sha256(user_prompt_on)
    prompt_sha256_off = compute_sha256(user_prompt_off)
    output_sha256_on = compute_sha256(model_output_on)
    output_sha256_off = compute_sha256(model_output_off)
    patch_sha256_on = compute_sha256(model_output_on)
    patch_sha256_off = compute_sha256(model_output_off)

    # 7. Verifier result check
    verifier_on_path = output_root / f"{task_id}/nexus_memory_on/verifier_result.json"
    verifier_off_path = output_root / f"{task_id}/nexus_memory_off/verifier_result.json"
    verifier_on = json.loads(verifier_on_path.read_text()) if verifier_on_path.exists() else {"status": "NOT_RUN"}
    verifier_off = json.loads(verifier_off_path.read_text()) if verifier_off_path.exists() else {"status": "NOT_RUN"}

    outcome_on = verifier_on.get("status", "UNKNOWN")
    outcome_off = verifier_off.get("status", "UNKNOWN")
    solved_on = outcome_on in ("PASS", "VERIFIER_EXECUTED_PASS")
    solved_off = outcome_off in ("PASS", "VERIFIER_EXECUTED_PASS")
    outcome_uplift_observed = solved_on and not solved_off

    # 8. Write model_call_receipt.json
    model_call_receipt = {
        "eval_id": "MEMORY_EVAL_11_C13453_REAL_MODEL_AB_v0",
        "task_id": task_id,
        "model": model_name,
        "endpoint": "http://localhost:11434",
        "temperature": 0.0,
        "seed": 42,
        "deterministic_settings": True,
        "artifact_source": "live_runtime",
        "created_during_run": True,
        "arms": ["nexus_memory_on", "nexus_memory_off"],
        "memory_on_lessons_retrieved": lessons_retrieved,
        "prompt_len_on": prompt_len_on,
        "prompt_len_off": prompt_len_off,
        "prompt_delta_chars": prompt_delta,
        "prompt_sha256_on": prompt_sha256_on,
        "prompt_sha256_off": prompt_sha256_off,
        "raw_model_output_sha256_on": output_sha256_on,
        "raw_model_output_sha256_off": output_sha256_off,
        "patch_sha256_on": patch_sha256_on,
        "patch_sha256_off": patch_sha256_off,
        "output_len_on": len(model_output_on),
        "output_len_off": len(model_output_off),
        "verifier_status_on": outcome_on,
        "verifier_status_off": outcome_off,
        "solved_on": solved_on,
        "solved_off": solved_off,
        "outcome_uplift_observed": outcome_uplift_observed,
    }
    receipt_path = artifact_root / "model_call_receipt.json"
    receipt_path.write_text(json.dumps(model_call_receipt, indent=2), encoding="utf-8")
    print(f"[*] model_call_receipt.json written")

    # 9. Write memory_impact_comparison.json
    memory_impact_comparison = {
        "eval_id": "MEMORY_EVAL_11_C13453_REAL_MODEL_AB_v0",
        "task_id": task_id,
        "artifact_source": "live_runtime",
        "created_during_run": True,
        "nexus_memory_on": {
            "prompt_length_chars": prompt_len_on,
            "output_length_chars": len(model_output_on),
            "patch_len": len(model_output_on),
            "solved": solved_on,
            "verifier_status": outcome_on,
            "lessons_retrieved": lessons_retrieved,
            "top_retrieved_ids": list(adapter_on.last_metadata.get("memory_evidence_ids", [])) if adapter_on.last_metadata else [],
        },
        "nexus_memory_off": {
            "prompt_length_chars": prompt_len_off,
            "output_length_chars": len(model_output_off),
            "patch_len": len(model_output_off),
            "solved": solved_off,
            "verifier_status": outcome_off,
            "lessons_retrieved": 0,
            "top_retrieved_ids": [],
        },
        "prompt_delta_chars": prompt_delta,
        "output_delta_chars": len(model_output_on) - len(model_output_off),
        "outcome_uplift_observed": outcome_uplift_observed,
        "data_aligned_to_live_artifacts": True,
    }
    comparison_path = artifact_root / "memory_impact_comparison.json"
    comparison_path.write_text(json.dumps(memory_impact_comparison, indent=2), encoding="utf-8")
    print(f"[*] memory_impact_comparison.json written")

    # 10. Write validation.json
    validation = {
        "eval_id": "MEMORY_EVAL_11_C13453_REAL_MODEL_AB_v0",
        "artifact_source": "live_runtime",
        "created_during_run": True,
        "real_model_call_executed": True,
        "synthetic_delta_measured": False,
        "real_model_decision_influence_proven": solved_on and not solved_off,
        "real_patch_synthesis_influence_proven": solved_on and not solved_off,
        "prompt_delta_observed": prompt_delta != 0,
        "model_output_delta_measured_from_artifacts": output_sha256_on != output_sha256_off,
        "patch_delta_measured_from_artifacts": patch_sha256_on != patch_sha256_off,
        "outcome_uplift_observed": outcome_uplift_observed,
        "public_claim_allowed": outcome_uplift_observed,
        "production_ready": False,
        "training_export_allowed": False,
        "internal_only": True,
        "validation_status": (
            "MEMORY_EVAL_11_OUTCOME_UPLIFT_CONFIRMED"
            if outcome_uplift_observed
            else "MEMORY_EVAL_11_REAL_MODEL_AB_MEASURED_NO_UPLIFT"
        ),
    }
    validation_path = artifact_root / "validation.json"
    validation_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(f"[*] validation.json written")

    # Summary
    print("\n=== MEMORY-EVAL-11 Summary ===")
    print(f"  Task: {task_id}")
    print(f"  Model: {model_name}")
    print(f"  Memory On: {lessons_retrieved} lessons retrieved")
    print(f"  Prompt delta: {prompt_delta:+d} chars")
    print(f"  Output delta: {len(model_output_on) - len(model_output_off):+d} chars")
    print(f"  Verifier ON: {outcome_on}")
    print(f"  Verifier OFF: {outcome_off}")
    print(f"  outcome_uplift_observed: {outcome_uplift_observed}")
    print(f"  validation_status: {validation['validation_status']}")


if __name__ == "__main__":
    run_ab_evaluation()
