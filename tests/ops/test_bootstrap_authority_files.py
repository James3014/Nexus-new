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
