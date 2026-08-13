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
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(
        encoding="utf-8"
    )

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
