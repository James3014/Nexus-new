"""
H8-8 Minimal Local Model Contract Stub Tests

Gate: H8-8 production contract stub boundary.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE
- NO_LOCAL_MODEL_RUN
- NO_OLLAMA_CALL / NO_QWEN_CALL
- NO_PROVIDER_CALL / NO_MODEL_CALL / NO_MODEL_LOAD / NO_NETWORK_CALL
- production_ready=false / public_claim_allowed=false
- H8 runtime not started
"""

from __future__ import annotations

import ast
import importlib
import sys

import pytest


def _load_contract_module():
    if "nexus.services.local_heal.local_model_adapter_contract" in sys.modules:
        del sys.modules["nexus.services.local_heal.local_model_adapter_contract"]
    mod = importlib.import_module(
        "nexus.services.local_heal.local_model_adapter_contract"
    )
    return mod


mod = _load_contract_module()


class TestH88ContractRequestSchema:
    def test_h8_8_contract_request_requires_task_candidate_evidence(self):
        req = mod.LocalModelAdapterRequest(
            task_id="t1",
            candidate_id="c1",
            evidence_refs=("ref://x",),
        )
        assert req.task_id == "t1"
        assert req.candidate_id == "c1"
        assert len(req.evidence_refs) == 1

    def test_h8_8_contract_receipt_requires_candidate_hash(self):
        req = mod.LocalModelAdapterRequest(selected_candidate_hash="sha256:abc")
        assert req.selected_candidate_hash.startswith("sha256:")

    def test_h8_8_contract_receipt_requires_evidence_refs(self):
        req = mod.LocalModelAdapterRequest(evidence_refs=("e1",))
        assert len(req.evidence_refs) > 0


class TestH88ResourcePolicyDeniesAll:
    def test_h8_8_resource_policy_denies_all_by_default(self):
        p = mod.LocalModelResourcePolicy()
        assert p.local_model_allowed is False
        assert p.model_load_allowed is False
        assert p.model_call_allowed is False
        assert p.provider_call_allowed is False
        assert p.network_allowed is False
        assert p.explicit_dry_run_approved is False


class TestH88ResponseDefaults:
    def test_h8_8_response_cannot_be_route_truth_by_default(self):
        resp = mod.LocalModelAdapterResponse()
        assert resp.adapter_output_is_route_truth is False
        assert resp.candidate_output_isolated is True
        assert resp.route_truth_source == "CapabilityPlanner"


class TestH88ReceiptDefaults:
    def test_h8_8_receipt_records_model_not_loaded_or_called(self):
        r = mod.LocalModelAdapterReceipt()
        assert r.local_model_loaded is False
        assert r.local_model_called is False
        assert r.model_load_allowed is False
        assert r.model_call_allowed is False

    def test_h8_8_receipt_public_claim_and_production_ready_false(self):
        r = mod.LocalModelAdapterReceipt()
        assert r.public_claim_allowed is False
        assert r.production_ready is False

    def test_h8_8_contract_keeps_route_truth_source_external(self):
        r = mod.LocalModelAdapterReceipt()
        assert r.route_truth_source == "CapabilityPlanner"
        assert r.adapter_output_is_route_truth is False


class TestH88ModuleSafety:
    def test_h8_8_contract_module_has_no_provider_imports(self):
        mod_path = (
            "nexus/services/local_heal/local_model_adapter_contract.py"
        )
        with open(mod_path, "r") as f:
            source = f.read()
        tree = ast.parse(source)
        forbidden = {
            "ollama",
            "transformers",
            "llama_cpp",
            "openai",
            "google",
            "requests",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in forbidden, f"forbidden import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    assert top not in forbidden, f"forbidden import from: {node.module}"

    def test_h8_8_contract_module_has_no_model_execution_surface(self):
        mod_path = (
            "nexus/services/local_heal/local_model_adapter_contract.py"
        )
        with open(mod_path, "r") as f:
            source = f.read()
        forbidden_patterns = [
            "subprocess",
            "os.system",
            "os.popen",
            "model.load",
            "model.call",
            "ollama.generate",
            "requests.get",
            "requests.post",
        ]
        for pat in forbidden_patterns:
            assert pat.lower() not in source.lower(), f"forbidden pattern: {pat}"
