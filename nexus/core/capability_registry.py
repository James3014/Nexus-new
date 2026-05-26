from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CapabilityInfo:
    """Canonical metadata representing a specific Nexus system capability."""

    name: str
    phases: List[str]  # Sublist of S,P,X,D,R,A,C
    cost_weight: float  # Scale 0.0 to 1.0
    maturity: str  # 'ACTIVE', 'BETA', 'EXPERIMENTAL'
    default_skill: str
    allowed_heep_modes: List[str] = field(default_factory=lambda: ["Mode B"])
    dependencies: List[str] = field(default_factory=list)


class CapabilityRegistry:
    """🏰 Source of Truth for all 34 capabilities in Nexus Autonomic Ecosystem."""

    # 34 Canonical Capabilities defined in NEXUS_CAPABILITY_SKILL_MAP.md
    _REGISTRY: Dict[str, CapabilityInfo] = {
        "artifact_gate": CapabilityInfo(
            name="artifact_gate",
            phases=["A"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="sf-systematic-artifact_gate-differential-review-461fbd0c",
            allowed_heep_modes=["Mode C"],
        ),
        "autonomic_router": CapabilityInfo(
            name="autonomic_router",
            phases=["P"],
            cost_weight=0.1,
            maturity="ACTIVE",
            default_skill="nexus-agent-execution-board-failclosed",
            allowed_heep_modes=["Mode B"],
        ),
        "autoreason": CapabilityInfo(
            name="autoreason",
            phases=["D"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="sf2-belief-route-fit-spec",
            allowed_heep_modes=["Mode B"],
        ),
        "belief": CapabilityInfo(
            name="belief",
            phases=["D"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="sf2-belief-route-fit-spec",
            allowed_heep_modes=["Mode B"],
        ),
        "benchmark_meta_opt": CapabilityInfo(
            name="benchmark_meta_opt",
            phases=["C"],
            cost_weight=0.4,
            maturity="ACTIVE",
            default_skill="sf-systematic-benchmark_meta_opt-hugging-face-trackio-d21c6b90",
            allowed_heep_modes=["Mode C"],
        ),
        "claim_gate": CapabilityInfo(
            name="claim_gate",
            phases=["A"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="addy-doubt-driven-development",
            allowed_heep_modes=["Mode B"],
        ),
        "codeintel": CapabilityInfo(
            name="codeintel",
            phases=["X"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="gstack-qa",
            allowed_heep_modes=["Mode C"],
        ),
        "ddtree": CapabilityInfo(
            name="ddtree",
            phases=["R"],
            cost_weight=0.4,
            maturity="ACTIVE",
            default_skill="nexus-root-cause-probe",
            allowed_heep_modes=["Mode B"],
        ),
        "direct_master_loop": CapabilityInfo(
            name="direct_master_loop",
            phases=["R"],
            cost_weight=0.5,
            maturity="ACTIVE",
            default_skill="sf-systematic-direct_master_loop-build-32802a87",
            allowed_heep_modes=["Mode A"],
        ),
        "drone": CapabilityInfo(
            name="drone",
            phases=["R"],
            cost_weight=0.4,
            maturity="ACTIVE",
            default_skill="sf-systematic-drone-python-background-jobs-18326a62",
            allowed_heep_modes=["Mode A"],
        ),
        "external_productivity": CapabilityInfo(
            name="external_productivity",
            phases=["R"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="aibdd.auto.python.e2e.green",
            allowed_heep_modes=["Mode A"],
        ),
        "file_lock_security_gate": CapabilityInfo(
            name="file_lock_security_gate",
            phases=["S"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="browserbase-what-antibot",
            allowed_heep_modes=["Mode C"],
        ),
        "forecast_pregate": CapabilityInfo(
            name="forecast_pregate",
            phases=["P"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="addy-shipping-and-launch",
            allowed_heep_modes=["Mode B"],
        ),
        "governance_and_trust": CapabilityInfo(
            name="governance_and_trust",
            phases=["S"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="sf-systematic-governance_and_trust-aegisops-ai-0aa841e2",
            allowed_heep_modes=["Mode C"],
        ),
        "hyper_sprint": CapabilityInfo(
            name="hyper_sprint",
            phases=["R"],
            cost_weight=0.8,
            maturity="ACTIVE",
            default_skill="retro",
            allowed_heep_modes=["Mode A"],
        ),
        "lancedb": CapabilityInfo(
            name="lancedb",
            phases=["X"],
            cost_weight=0.1,
            maturity="ACTIVE",
            default_skill="research-source-validation-auditor",
            allowed_heep_modes=["Mode B"],
        ),
        "learn_ask": CapabilityInfo(
            name="learn_ask",
            phases=["C"],
            cost_weight=0.4,
            maturity="ACTIVE",
            default_skill="nexus-live-ask-replay-normalization-gate",
            allowed_heep_modes=["Mode C"],
        ),
        "learning_closure": CapabilityInfo(
            name="learning_closure",
            phases=["C"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="sf-systematic-learning_closure-memory-lint-8bdb0fca",
            allowed_heep_modes=["Mode C"],
        ),
        "memory": CapabilityInfo(
            name="memory",
            phases=["X"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="product-self-knowledge",
            allowed_heep_modes=["Mode B"],
        ),
        "mempalace": CapabilityInfo(
            name="mempalace",
            phases=["S"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="sf2-mempalace-route-fit-spec",
            allowed_heep_modes=["Mode B"],
        ),
        "metabolism_resume": CapabilityInfo(
            name="metabolism_resume",
            phases=["C"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="addy-shipping-and-launch",
            allowed_heep_modes=["Mode A"],
        ),
        "nightshift": CapabilityInfo(
            name="nightshift",
            phases=["R"],
            cost_weight=0.5,
            maturity="ACTIVE",
            default_skill="canary",
            allowed_heep_modes=["Mode A"],
        ),
        "policy_capability_gate": CapabilityInfo(
            name="policy_capability_gate",
            phases=["S"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="browse",
            allowed_heep_modes=["Mode C"],
        ),
        "registry_skills_sync": CapabilityInfo(
            name="registry_skills_sync",
            phases=["P"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="gstack-sync-gbrain",
            allowed_heep_modes=["Mode B"],
        ),
        "regression_guard": CapabilityInfo(
            name="regression_guard",
            phases=["A"],
            cost_weight=0.4,
            maturity="ACTIVE",
            default_skill="sf-systematic-regression_guard-odoo-automated-tests-dad98433",
            allowed_heep_modes=["Mode B"],
        ),
        "repair_loop": CapabilityInfo(
            name="repair_loop",
            phases=["R"],
            cost_weight=0.5,
            maturity="ACTIVE",
            default_skill="qa-only",
            allowed_heep_modes=["Mode B"],
        ),
        "research": CapabilityInfo(
            name="research",
            phases=["X"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="gbrain-academic-verify",
            allowed_heep_modes=["Mode C"],
        ),
        "research_and_source_discipline": CapabilityInfo(
            name="research_and_source_discipline",
            phases=["X"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="gbrain-maintain",
            allowed_heep_modes=["Mode C"],
        ),
        "research_control_plane": CapabilityInfo(
            name="research_control_plane",
            phases=["X"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="browserbase-fetch",
            allowed_heep_modes=["Mode C"],
        ),
        "sandbox_replay": CapabilityInfo(
            name="sandbox_replay",
            phases=["A"],
            cost_weight=0.4,
            maturity="ACTIVE",
            default_skill="nexus-acceptance-evidence-gate",
            allowed_heep_modes=["Mode B"],
        ),
        "swarm_multi_agent": CapabilityInfo(
            name="swarm_multi_agent",
            phases=["R"],
            cost_weight=0.6,
            maturity="ACTIVE",
            default_skill="nexus-gemini-code-review-orchestrator",
            allowed_heep_modes=["Mode C"],
        ),
        "ui_validator": CapabilityInfo(
            name="ui_validator",
            phases=["A"],
            cost_weight=0.4,
            maturity="BETA",
            default_skill="sf-systematic-ui_validator-e2e-testing-d98eb7c3",
            allowed_heep_modes=["Mode B"],
        ),
        "ultra_review": CapabilityInfo(
            name="ultra_review",
            phases=["A"],
            cost_weight=0.5,
            maturity="ACTIVE",
            default_skill="github11-vulnerability-scanner-ultra-review",
            allowed_heep_modes=["Mode C"],
        ),
        "xray": CapabilityInfo(
            name="xray",
            phases=["X"],
            cost_weight=0.3,
            maturity="ACTIVE",
            default_skill="diagnose",
            allowed_heep_modes=["Mode B"],
        ),
    }

    def __init__(self) -> None:
        pass

    def get_capability(self, name: str) -> Optional[CapabilityInfo]:
        """Lookup canonical capability by its name identifier."""
        return self._REGISTRY.get(str(name).strip().lower())

    def list_capabilities(self, phase: Optional[str] = None) -> List[CapabilityInfo]:
        """List all capabilities, optionally filtered by S,P,X,D,R,A,C phase sublist."""
        if not phase:
            return list(self._REGISTRY.values())
        phase_upper = str(phase).strip().upper()
        return [cap for cap in self._REGISTRY.values() if phase_upper in cap.phases]

    def list_all_capabilities(self) -> List[CapabilityInfo]:
        """List all 34 capabilities registered in Nexus."""
        return list(self._REGISTRY.values())
