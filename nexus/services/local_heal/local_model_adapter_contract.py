"""
H8-8 Minimal Local Model Adapter Contract Stub

Inert deny-by-default contract for future local model solve path.
No provider, model, network, or runtime imports.
No model load or execution surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LocalModelAdapterRequest:
    request_id: str = ""
    task_id: str = ""
    candidate_id: str = ""
    selected_candidate_hash: str = ""
    evidence_refs: tuple[str, ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    forbidden_capabilities: tuple[str, ...] = (
        "provider_call",
        "network",
        "model_load",
        "model_call",
    )
    route_truth_source: str = "CapabilityPlanner"


@dataclass(frozen=True)
class LocalModelAdapterResponse:
    fake_adapter: bool = True
    candidate_id: str = ""
    selected_candidate_hash: str = ""
    adapter_output: str = ""
    candidate_output_isolated: bool = True
    adapter_output_is_route_truth: bool = False
    route_truth_source: str = "CapabilityPlanner"
    local_model_provider: str = "fake"
    local_model_name: str = "fake"
    local_model_loaded: bool = False
    local_model_called: bool = False
    model_load_allowed: bool = False
    model_call_allowed: bool = False
    provider_call_allowed: bool = False
    network_allowed: bool = False
    verifier_result: str = "not_run"
    public_claim_allowed: bool = False
    production_ready: bool = False


@dataclass(frozen=True)
class LocalModelAdapterReceipt:
    receipt_id: str = ""
    request_id: str = ""
    fake_adapter: bool = True
    candidate_id: str = ""
    selected_candidate_hash: str = ""
    local_model_provider: str = "fake"
    local_model_name: str = "fake"
    local_model_allowed: bool = False
    local_model_loaded: bool = False
    local_model_called: bool = False
    local_model_denied_reason: str = "deny_by_default"
    provider_call_allowed: bool = False
    network_allowed: bool = False
    model_load_allowed: bool = False
    model_call_allowed: bool = False
    adapter_output_is_route_truth: bool = False
    candidate_output_isolated: bool = True
    route_truth_source: str = "CapabilityPlanner"
    evidence_refs: tuple[str, ...] = ()
    verifier_result: str = "not_run"
    public_claim_allowed: bool = False
    production_ready: bool = False


@dataclass(frozen=True)
class LocalModelResourcePolicy:
    local_model_allowed: bool = False
    model_load_allowed: bool = False
    model_call_allowed: bool = False
    provider_call_allowed: bool = False
    network_allowed: bool = False
    explicit_dry_run_approved: bool = False
