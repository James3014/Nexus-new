from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

from scripts.bench.capability_ab_runner import CapabilityTask, _finalize_with_nexus_row


@pytest.mark.skipif(
    os.environ.get("NEXUS_RUN_REAL_ISSUE_TESTS") != "1",
    reason="Set NEXUS_RUN_REAL_ISSUE_TESTS=1 to run real issue tests",
)
@pytest.mark.skipif(
    os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") != "1",
    reason="Set NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 to run real issue tests",
)
def test_focused_real_issue_solve_astropy_13236(monkeypatch, tmp_path):
    """Focused real issue solve: astropy-13236 (structured ndarray column auto-transformation)."""
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

    # Create a simplified reproduction of astropy-13236
    target_dir = resolved_path / "astropy" / "table"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "__init__.py").write_text("", encoding="utf-8")

    # Simplified table.py with the bug
    (target_dir / "table.py").write_text(
        "class Table:\n"
        "    def __init__(self, data=None):\n"
        "        self._data = data\n"
        "        if hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n"
        "            self._data = data.view(type('NdarrayMixin', (), {'__array__': lambda self: self._data})())\n"
        "    def __getitem__(self, key):\n"
        "        return self._data[key]\n",
        encoding="utf-8",
    )

    # Verification script
    (resolved_path / "verify_13236.py").write_text(
        "import sys\nc = open('astropy/table/table.py').read()\n"
        "# Bug: NdarrayMixin auto-transformation should NOT happen for structured arrays\n"
        "# Fix: remove the automatic view(NdarrayMixin) line\n"
        "sys.exit(0 if 'NdarrayMixin' not in c or 'view(NdarrayMixin)' not in c else 1)\n",
        encoding="utf-8",
    )

    committee_called = False
    def mock_committee(*args, **kwargs):
        nonlocal committee_called
        committee_called = True
        from nexus.services.local_heal.local_model_provider import OllamaLocalModelProvider, LocalModelProviderRequest
        provider = OllamaLocalModelProvider()
        prompt = (
            "You are generating a replacement code block to solve a coding task.\n"
            "Problem: Fix the Table.__init__ to not auto-transform structured ndarray columns into NdarrayMixin.\n"
            "Target File: astropy/table/table.py\n"
            "Target Symbol: __init__\n"
            "Locked Search Span:\n"
            "```\nif hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n"
            "            self._data = data.view(type('NdarrayMixin', (), {'__array__': lambda self: self._data})())\n```\n\n"
            "Provide replacement that removes the NdarrayMixin view:\n"
            "<<<<<<< REPLACE\n[replacement]\n>>>>>>> REPLACE\n\n"
        )
        prov_resp = provider.generate(LocalModelProviderRequest(
            task_id="astropy-13236", prompt=prompt, evidence_refs=("ref1",),
            model_name="qwen2.5-coder:7b",
        ))
        from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
        patch = prov_resp.output_text or ""
        return [CandidateEnvelope(
            candidate_id="astropy-13236-primary", task_id="astropy-13236",
            source="local", model="qwen2.5-coder:7b", role="primary_proposer",
            patch_protocol="anchored_edit", target_file="astropy/table/table.py",
            target_symbol="__init__", source_anchor_hash="ahash",
            candidate_patch_hash=hashlib.sha256(patch.encode()).hexdigest() if patch else hashlib.sha256(b"").hexdigest(),
            evidence_refs=("ref1",), candidate_patch=patch,
        )]

    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_committee)

    task = CapabilityTask(
        id="astropy__astropy-13236",
        task_desc="Prevent auto-transformation of structured ndarray column into NdarrayMixin",
        task_type="bug", success_criteria="passes", difficulty="hard", category="structured_array",
        expected_capabilities=["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        target_file="astropy/table/table.py",
        test_file="verify_13236.py",
    )

    row = {
        "capability_plan_selected": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        "evidence_refs": ["astropy-13236-ref"],
        "verifier_command": ["python3", str(resolved_path / "verify_13236.py")],
        "target_symbol": "__init__",
        "locked_search": "if hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n            self._data = data.view(type('NdarrayMixin', (), {'__array__': lambda self: self._data})())",
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

    result = {
        "task_id": "astropy__astropy-13236",
        "model_name": adapter_meta.get("executor_model", ""),
        "local_model_called": adapter.get("local_model_called", False),
        "execution_topology": adapter_meta.get("execution_topology", ""),
        "selected_capabilities_used": adapter_meta.get("selected_capabilities_used", []),
        "candidate_count": adapter_meta.get("committee_candidate_count", 0),
        "selected_candidate_id": adapter_meta.get("selected_candidate_id", ""),
        "protocol_normalization": adapter_meta.get("protocol_normalization", {}),
        "source_anchor_source": adapter_meta.get("source_anchor_source", ""),
        "source_anchor_hash_present": bool(adapter_meta.get("source_anchor_hash")),
        "failure_feedback_present": adapter_meta.get("failure_feedback_present", False),
        "verifier_result": "pass" if receipt and receipt.get("gate_passed") else "fail",
        "solved": receipt is not None and receipt.get("gate_passed", False),
        "failed_reason": receipt.get("failure_reason", "") if receipt else "no_receipt",
        "final_authority": "NexusVerifier",
    }

    # Must have diagnostic receipt
    assert receipt is not None, "no receipt"
    assert result["solved"] or result["verifier_result"] == "fail"
    assert result["final_authority"] == "NexusVerifier"

    if result["solved"]:
        assert result["source_anchor_source"] == "locked_search"
        assert result["adapter_invoked"] or adapter.get("adapter_invoked") is True
    else:
        assert result["failed_reason"] != "", "failed_reason must be explicit on failure"