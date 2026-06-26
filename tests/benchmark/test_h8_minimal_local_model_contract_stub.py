"""
H8-8 Minimal Local Model Contract Stub Tests

Gate: H8 minimal inert production contract stub.
All tests verify deny-by-default and no provider/model surface.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from nexus.services.local_heal.local_model_adapter_contract import (
    LocalModelAdapterReceipt,
    LocalModelAdapterRequest,
    LocalModelAdapterResponse,
    LocalModelResourcePolicy,
)


class TestH88Request:
    def test_h8_8_contract_request_requires_task_candidate_evidence(self):
        r = LocalModelAdapterRequest(
            task_id="t1",
            candidate_id="c1",
            evidence_refs=("e1",),
        )
        assert r.task_id != ""
        assert r.candidate_id != ""
        assert len(r.evidence_refs) > 0


class TestH88ResourcePolicy:
    def test_h8_8_resource_policy_denies_all_by_default(self):
        p = LocalModelResourcePolicy()
        assert p.local_model_allowed is False
        assert p.model_load_allowed is False
        assert p.model_call_allowed is False
        assert p.provider_call_allowed is False
        assert p.network_allowed is False
        assert p.explicit_dry_run_approved is False


class TestH88Response:
    def test_h8_8_response_cannot_be_route_truth_by_default(self):
        r = LocalModelAdapterResponse()
        assert r.adapter_output_is_route_truth is False
        assert r.route_truth_source == "CapabilityPlanner"


class TestH88Receipt:
    def test_h8_8_receipt_records_model_not_loaded_or_called(self):
        r = LocalModelAdapterReceipt()
        assert r.local_model_loaded is False
        assert r.local_model_called is False

    def test_h8_8_receipt_public_claim_and_production_ready_false(self):
        r = LocalModelAdapterReceipt()
        assert r.public_claim_allowed is False
        assert r.production_ready is False

    def test_h8_8_contract_receipt_requires_candidate_hash(self):
        r = LocalModelAdapterReceipt(selected_candidate_hash="sha256:x")
        assert r.selected_candidate_hash.startswith("sha256:")

    def test_h8_8_contract_receipt_requires_evidence_refs(self):
        r = LocalModelAdapterReceipt(evidence_refs=("receipt://test",))
        assert len(r.evidence_refs) > 0

    def test_h8_8_contract_keeps_route_truth_source_external(self):
        r = LocalModelAdapterReceipt()
        assert r.route_truth_source == "CapabilityPlanner"
        assert r.adapter_output_is_route_truth is False


class TestH88ModuleSafety:
    def test_h8_8_contract_module_has_no_provider_imports(self):
        mod = importlib.import_module(
            "nexus.services.local_heal.local_model_adapter_contract"
        )
        source = importlib.util.find_spec(mod.__name__).origin
        with open(source) as f:
            content = f.read()
        for forbidden in [
            "import ollama",
            "import transformers",
            "import llama_cpp",
            "import openai",
            "import google.generativeai",
            "import requests",
        ]:
            assert forbidden not in content, f"Found forbidden import: {forbidden}"

    def test_h8_8_contract_module_has_no_model_execution_surface(self):
        mod = importlib.import_module(
            "nexus.services.local_heal.local_model_adapter_contract"
        )
        source = importlib.util.find_spec(mod.__name__).origin
        with open(source) as f:
            content = f.read()
        for forbidden in [
            "subprocess",
            "model.generate",
            "model.load",
            "model.call",
            "requests.get",
            "requests.post",
        ]:
            assert forbidden not in content, f"Found forbidden surface: {forbidden}"
