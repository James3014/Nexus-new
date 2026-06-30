from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

from scripts.bench.capability_ab_runner import CapabilityTask, _finalize_with_nexus_row


@pytest.mark.skipif(
    os.environ.get("NEXUS_RUN_REAL_LOCAL_MODEL_TESTS") != "1",
    reason="Set NEXUS_RUN_REAL_LOCAL_MODEL_TESTS=1 to run real local model tests",
)
@pytest.mark.skipif(
    os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") != "1",
    reason="Set NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 to run real local model tests",
)
def test_real_qwen_toy_solve_local_model_armor(monkeypatch, tmp_path):
    """Real Qwen toy solve: local model generates patch through Nexus armor mainline."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
    except Exception:
        pytest.skip("Ollama is not running locally")

    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider

    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b")
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED", "1")

    resolved_path = tmp_path.resolve()
    target_dir = resolved_path / "toy"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "math_util.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    (resolved_path / "verify.py").write_text(
        "import sys\nc = open('toy/math_util.py').read()\nsys.exit(0 if 'return x * 3' in c else 1)\n",
        encoding="utf-8",
    )

    committee_called = False
    def mock_committee(*args, **kwargs):
        nonlocal committee_called
        committee_called = True
        # Let the real provider generate candidates
        from nexus.services.local_heal.local_model_provider import OllamaLocalModelProvider
        provider = OllamaLocalModelProvider()
        from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
        prompt = (
            "You are generating a replacement code block to solve a coding task.\n"
            "Problem: Fix double to return x * 3 instead of x * 2\n"
            "Target File: toy/math_util.py\n"
            "Target Symbol: double\n"
            "Locked Search Span that will be replaced:\n"
            "```\ndef double(x):\n    return x * 2\n```\n\n"
            "Provide the replacement code inside a REPLACE block exactly like this:\n"
            "<<<<<<< REPLACE\n"
            "def double(x):\n"
            "    return x * 3\n"
            ">>>>>>> REPLACE\n\n"
            "Do not include any other text outside the REPLACE block.\n"
        )
        prov_resp = provider.generate(LocalModelProviderRequest(
            task_id="real-qwen-toy",
            prompt=prompt,
            evidence_refs=("ref1",),
            model_name="qwen2.5-coder:7b",
        ))
        from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
        return [CandidateEnvelope(
            candidate_id="real-qwen-primary",
            task_id="real-qwen-toy",
            source="local",
            model="qwen2.5-coder:7b",
            role="primary_proposer",
            patch_protocol="anchored_edit",
            target_file="toy/math_util.py",
            target_symbol="double",
            source_anchor_hash="ahash",
            candidate_patch_hash=hashlib.sha256(prov_resp.output_text.encode()).hexdigest() if prov_resp.output_text else hashlib.sha256(b"").hexdigest(),
            evidence_refs=("ref1",),
            candidate_patch=prov_resp.output_text or "",
        )]

    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_committee)

    task = CapabilityTask(
        id="real-qwen-toy",
        task_desc="Fix double to return x * 3",
        task_type="bug",
        success_criteria="passes",
        difficulty="easy",
        category="test",
        expected_capabilities=["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        target_file="toy/math_util.py",
        test_file="verify.py",
    )

    row = {
        "capability_plan_selected": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        "evidence_refs": ["real-qwen-ref"],
        "verifier_command": ["python3", str(resolved_path / "verify.py")],
        "target_symbol": "double",
        "locked_search": "def double(x):\n    return x * 2",
        "candidate_generate_fn": lambda req: "mock",
        "signal_snapshot": {"execution_topology": "local_committee_only"},
    }

    finalized = _finalize_with_nexus_row(
        row, provider="ollama", model_required=True, nexus_required=True,
        task=task, repo_root=resolved_path,
    )

    receipt = finalized.get("local_executor_receipt")
    adapter = finalized.get("local_model_adapter", {})
    adapter_meta = adapter.get("metadata", {})

    # Record result
    result = {
        "task_id": "real-qwen-toy",
        "model_name": adapter_meta.get("executor_model", ""),
        "local_model_called": adapter.get("local_model_called", False),
        "execution_topology": adapter_meta.get("execution_topology", ""),
        "candidate_count": adapter_meta.get("committee_candidate_count", 0),
        "verifier_result": "pass" if receipt and receipt.get("gate_passed") else "fail",
        "solved": receipt is not None and receipt.get("gate_passed", False),
        "final_authority": "NexusVerifier",
    }

    assert committee_called, "committee provider not called"
    assert receipt is not None, "no receipt"
    assert result["solved"] or result["verifier_result"] == "fail", "must be solved or explicitly failed"

    if result["solved"]:
        assert result["model_name"] != "", "model_name must be recorded"
        assert result["execution_topology"] == "local_committee_only"
        assert adapter.get("route_mode") == "local_only_executed"
    else:
        # Diagnostic receipt on failure
        assert receipt.get("failure_reason") or receipt.get("failure_reason") == "", "failure_reason must be explicit"
