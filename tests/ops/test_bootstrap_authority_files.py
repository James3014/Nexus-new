from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILES = (
    "AGENTS.md",
    "MUSE_PROTO.md",
    "GEMINI.md",
    ".gemini/GEMINI.md",
    "CLAUDE.md",
    "MEMORY.md",
    "SOUL.md",
    ".cursorrules",
)
FORBIDDEN_TOKENS = (
    "nexus-sync",
    "STATE.yaml",
    "Nexus-Singularity-V17",
    "Nexus-Singularity-V26",
    "AGENT_MANDATORY_PROTOCOL.md",
    "/Users/jameschen/Workspace/nexus/",
    '--filter "domain=tech"',
)
AUTHORITY_FILES = (
    "AGENTS.md",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "docs/agents/WORKFORCE_EXECUTION_OVERLAY.md",
)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _authority_texts() -> dict[str, str]:
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in AUTHORITY_FILES}


def test_bootstrap_files_use_current_worktree_authority():
    contents = {path: (ROOT / path).read_text(encoding="utf-8") for path in BOOTSTRAP_FILES}
    for path, content in contents.items():
        assert not any(token in content for token in FORBIDDEN_TOKENS), path

    assert "active Git-tracked Task Card" in contents["AGENTS.md"]
    assert "DIRECT_CANONICAL" in contents["AGENTS.md"]
    assert "does not require a Task Card" in contents["AGENTS.md"]
    for path in ("GEMINI.md", "CLAUDE.md", "MEMORY.md", "SOUL.md", ".cursorrules"):
        assert "DIRECT_CANONICAL" in contents[path], path
    assert "MUSE_PROTO.md` is only" in contents["MUSE_PROTO.md"]
    assert "../GEMINI.md" in contents[".gemini/GEMINI.md"]


def test_execution_domains_and_candidate_namespaces_are_unambiguous():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    launch = (ROOT / ".agents/skills/nexus-task-launch/SKILL.md").read_text(encoding="utf-8")
    merge = (ROOT / ".agents/skills/nexus-merge-gate/SKILL.md").read_text(encoding="utf-8")

    assert "The Owner chooses the execution lane" in agents
    assert "does not select local lifecycle" in agents
    assert "A GitHub PR Candidate" in agents
    assert "a local lifecycle Candidate" in agents
    assert "never substitutes for program correctness" in agents
    assert "Reviewer block/card omission is not\n  terminal `REJECTED`" in agents

    assert "GitHub collaboration and local lifecycle domains" in contract
    assert "does not enter local lifecycle merely because it is\ndelegated" in contract
    assert "not the admission or merge gate for ordinary GitHub PR work" in contract
    assert "must not create, widen, or recursively bootstrap" in contract
    assert "not automatically a\nterminal `REJECTED` Candidate" in contract

    assert "This skill governs only the\nlocal Nexus self-hosted lifecycle" in launch
    assert "Ordinary GitHub\nReady-Issue branch work does not enter this skill" in launch
    assert "That handoff applies only to a local lifecycle Candidate" in launch

    assert "applies exclusively to a local Nexus lifecycle Candidate" in merge
    assert "It is not the merge procedure for a GitHub PR Candidate" in merge


def test_ready_issue_claim_contract_is_worker_neutral_and_fail_closed():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")

    assert "eligible governed worker" in agents
    assert "Provider/model names are not normative" in agents
    for token in (
        "claim_intent",
        "claim_enforcement_state",
        "claim_mode",
        "PROJECTION_ONLY",
        "UNKNOWN",
        "MANUAL_DISPATCH",
        "assignees, labels, comments, Project fields, branch names",
    ):
        assert token in agents
        if token != "assignees, labels, comments, Project fields, branch names":
            assert token in contract
    assert "GitHub UI metadata and branch names remain" in contract
    assert "canonical atomic/fenced claim operation" in contract
    assert "never grants\n  route selection" in contract


def test_protected_merge_preserves_standing_grant_across_normal_phases():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")
    merge = (ROOT / ".agents/skills/nexus-merge-gate/SKILL.md").read_text(encoding="utf-8")
    current = (
        ROOT / "tasks/standing-owner-autonomy-20260811/02-standing-grant-normal-phase-authority.md"
    ).read_text(encoding="utf-8")
    historical_card = (
        ROOT / "tasks/standing-owner-autonomy-20260811/01-standing-coordinator-authority.md"
    ).read_text(encoding="utf-8")

    assert "valid\n  covered standing grant remains valid across normal workflow phase" in agents
    assert "normal\nGitHub workflow phases" in contract
    assert "bound to the exact repository, PR, head, and base" in agents
    assert "`MERGE_INTENT` is evidence" in agents
    assert "Any PR/head/base/main or evidence drift invalidates" in contract
    assert "valid\ncurrent standing grant explicitly covering" in merge
    assert "ordinary phases from Task Card through main" in current
    assert "PLATFORM_APPROVAL_REQUIRED" in current
    assert "status: HISTORICAL_SUPERSEDED_BY_ISSUE_163_NORMAL_PHASE_AUTHORITY" in historical_card
    assert "per-phase merge-slot restriction is historical and superseded" in historical_card


def test_current_standing_grant_contract_is_non_self_attesting():
    index = (ROOT / "tasks/standing-owner-autonomy-20260811/INDEX.md").read_text(
        encoding="utf-8"
    )
    current = (
        ROOT / "tasks/standing-owner-autonomy-20260811/02-standing-grant-normal-phase-authority.md"
    ).read_text(encoding="utf-8")

    assert "frontier: 02-standing-grant-normal-phase-authority.md" in index
    assert "normative CURRENT AUTHORITY CONTRACT" in current
    assert "does not itself attest" in current
    assert "does not itself authorize a merge" in current
    for field in (
        "grant_id",
        "owner",
        "primary coordinator",
        "repository",
        "source_thread",
        "Goal",
        "issued_at",
        "expiry",
        "revocation_state",
        "context_hash",
    ):
        assert f"`{field}`" in current
    assert "`GITHUB_MERGE`" in current
    assert "separate physical, machine-bound Owner receipt" in current


def test_bootstrap_file_set_is_complete_and_tracked():
    for path in BOOTSTRAP_FILES:
        assert (ROOT / path).is_file(), path


def test_external_bootstrap_recovery_boundary_is_fail_closed():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs/governance/rollback_runbook.md").read_text(encoding="utf-8")
    normalized_runbook = " ".join(runbook.split())

    assert "self-hosting/controller identity contract is itself under repair" in agents
    assert "bounded external bootstrap procedure" in agents
    assert "never implies approval, integration, push, reload, or activation" in agents

    for required in (
        "identity, action-authorization, or state-transition contract",
        "ordinary provider, model, quota, test",
        "correctly blocking healthy lifecycle failure",
        "normal governed path",
        "exact known-clean repository base",
        "external clean repair worktree",
        "Never copy a",
        "whole file or commit from a dirty canonical checkout",
        "exact parent, tree, and full diff",
        "source/runtime/action identity is missing, substituted, stale, or tampered",
        "positive, negative, tamper, retry/idempotency",
        "same `task_id`",
        "fresh `attempt_id`",
        "`action_id`, and `idempotency_key`",
        "must not create a second Controller",
        "independent review",
        "distinct from the implementer",
        "permanent alternative lifecycle",
        "`CapabilityPlanner` remains the sole route",
        "`HybridRouteDecision` remains only its derived decision projection",
    ):
        assert required in normalized_runbook

    assert "repair completion performs none of them" in normalized_runbook
    assert "Resume the normal governed path" in normalized_runbook


def test_direct_delegated_contract_is_explicit_and_bounded():
    texts = _authority_texts()
    agents = _norm(texts["AGENTS.md"])
    combined = _norm(" ".join(texts.values()))

    assert "DIRECT_DELEGATED" in agents
    assert "exactly one bounded external worker" in agents
    assert "No Nexus Task Card, Nexus lifecycle, CapabilityPlanner routing" in agents
    assert "Delegated implementation alone does not force governed execution" in agents
    assert "independently inspects the physical diff" in agents
    assert "AUTO_CHAIN=false" in agents
    assert "DIRECT_DELEGATED_BLOCKED" in combined
    assert (
        "direct external delegation boundary"
        in _norm(texts["docs/agents/WORKFORCE_EXECUTION_OVERLAY.md"]).lower()
    )
    assert (
        "Direct work becomes governed before mutation if it delegates implementation"
        not in texts["AGENTS.md"]
    )


def test_task_execution_contract_preserves_direct_delegated_exception():
    contract = _authority_texts()["docs/agents/TASK_EXECUTION_CONTRACT.md"]
    normalized = _norm(contract)

    assert "DIRECT_DELEGATED" in contract
    assert "not required solely because implementation is delegated" in normalized
    assert "exceeds the `DIRECT_DELEGATED` boundary" in normalized
    assert "Nexus lifecycle/Candidate authority" in normalized
    assert "changes route/lifecycle/workforce/security authority" in normalized
    assert "requires protected integration" in normalized
    assert "production/public claim" in normalized
    assert (
        "Escalate to this governed contract before mutation when implementation is delegated"
        not in contract
    )


def test_direct_external_delegation_does_not_inherit_nexus_workforce_admission():
    overlay = _authority_texts()["docs/agents/WORKFORCE_EXECUTION_OVERLAY.md"]
    normalized = _norm(overlay)

    assert "DIRECT_DELEGATED" in overlay
    assert "does NOT use Nexus Workforce Admission" in normalized
    assert (
        "Nexus runtime model execution always requires fresh Nexus Workforce Admission"
        in normalized
    )
    assert "transport/execution evidence only" in normalized
    assert "grants no Nexus" in normalized
    assert "route, admission, approval, integration, merge, release" in normalized
    assert "non-self-approving" in normalized
    assert "Local output and delegated output are candidates" in normalized
