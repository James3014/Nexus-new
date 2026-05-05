from __future__ import annotations

from typing import Any


RESEARCH_STACK_PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "id": "autoresearch",
        "source_path": "/Users/jameschen/Workspace/test/autoresearch",
        "capability": "fixed_budget_metric_loop",
        "checkpoint": "fixed_budget_metric_contract",
        "route_phase": "X",
    },
    {
        "id": "codex-autoresearch",
        "source_path": "/Users/jameschen/Workspace/test/codex-autoresearch",
        "capability": "packet_loop_asi_ledger",
        "checkpoint": "packet_session_ledger",
        "route_phase": "C",
    },
    {
        "id": "AutoResearchClaw",
        "source_path": "/Users/jameschen/Workspace/test/AutoResearchClaw",
        "capability": "deep_claim_literature_verification",
        "checkpoint": "claim_citation_verification",
        "route_phase": "X",
    },
    {
        "id": "autoreason",
        "source_path": "/Users/jameschen/Workspace/test/autoreason",
        "capability": "blind_borda_candidate_tournament",
        "checkpoint": "candidate_tournament_receipt",
        "route_phase": "D",
    },
)


def research_stack_contract() -> dict[str, Any]:
    projects = [dict(item) for item in RESEARCH_STACK_PROJECTS]
    return {
        "schema": "nexus_research_stack_contract_v1",
        "source_projects": [str(item["id"]) for item in projects],
        "checkpoints": [
            {
                "id": str(item["checkpoint"]),
                "source_project": str(item["id"]),
                "capability": str(item["capability"]),
                "route_phase": str(item["route_phase"]),
                "required_for_public_route": True,
            }
            for item in projects
        ],
        "projects": projects,
    }


def research_stack_source_projects() -> list[str]:
    return [str(item["id"]) for item in RESEARCH_STACK_PROJECTS]


def research_stack_checkpoint_ids() -> list[str]:
    return [str(item["checkpoint"]) for item in RESEARCH_STACK_PROJECTS]
