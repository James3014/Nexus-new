#!/usr/bin/env python3
"""Y2 — Controlled Multi-Anchor / Multi-File Protocol Generator script."""
import json
from pathlib import Path
from nexus.services.local_heal.action_protocol import ActionProtocol, ProtocolAction, ActionDependency

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
OUTPUT_DIR = REPO_ROOT / "artifacts" / "runtime" / "y2_controlled_multifile_protocol_v0"


def main():
    print("Running Y2 Protocol Generator...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Define safety policy
    safety_policy = {
        "max_ordered_actions": 5,
        "max_files_involved": 2,
        "enforced_rollback_policy": "git_checkout_discard",
        "restricted_types": {
            "TWO_FILE_COORDINATED_EDIT": {
                "owner_approval_required_by_default": True
            },
            "ABSTAIN_BOUNDARY_EDIT": {
                "always_abstain": True
            }
        }
    }
    with open(OUTPUT_DIR / "safety_policy.json", "w") as f:
        json.dump(safety_policy, f, indent=2)

    # 2. Build example for sympy-14096 (MULTI_ANCHOR_SEQUENCE)
    p1 = ActionProtocol(
        protocol_id="p_sympy-14096_v0",
        protocol_type="MULTI_ANCHOR_SEQUENCE",
        task_id="sympy__sympy-14096",
        rollback_policy="git_checkout_discard",
        verifier_required=True,
        owner_approval_required=False,
        files_involved=["sympy/core/power.py"]
    )
    a1 = ProtocolAction(
        action_id="act_1",
        file_path="sympy/core/power.py",
        anchor_symbol="Pow._eval_is_integer",
        exact_search_text="def _eval_is_integer(self):",
        replacement_text="def _eval_is_integer(self):\n        if self.exp.is_integer is False:\n            return False",
        evidence_node_id="n2"
    )
    p1.ordered_actions = [a1]

    # 3. Build example for django-11505 (TWO_FILE_COORDINATED_EDIT - Owner Gated)
    p2 = ActionProtocol(
        protocol_id="p_django-11505_v0",
        protocol_type="TWO_FILE_COORDINATED_EDIT",
        task_id="django__django-11505",
        rollback_policy="git_checkout_discard",
        verifier_required=True,
        owner_approval_required=True, # MUST be True for Two File Coordinated Edit
        files_involved=["django/contrib/messages/storage/base.py", "django/contrib/messages/storage/cookie.py"]
    )
    a2_1 = ProtocolAction(
        action_id="act_1",
        file_path="django/contrib/messages/storage/base.py",
        anchor_symbol="add",
        exact_search_text="def add(self, level, message, extra_tags='', request=None):",
        replacement_text="def add(self, level, message, extra_tags='', request=None):\n        if request is None:\n            request = self.request",
        evidence_node_id="n1"
    )
    a2_2 = ProtocolAction(
        action_id="act_2",
        file_path="django/contrib/messages/storage/cookie.py",
        anchor_symbol="_encode",
        exact_search_text="def _encode(self, messages):",
        replacement_text="def _encode(self, messages):\n        if not self.request:\n            raise SuspiciousOperation('Missing request Context')",
        evidence_node_id="n2"
    )
    p2.ordered_actions = [a2_1, a2_2]
    p2.dependency_edges = [
        ActionDependency(source_action_id="act_1", target_action_id="act_2", dependency_reason="Base storage request propagation must be set before cookie encode validation.")
    ]

    # Write examples
    examples = {
        "sympy__sympy-14096": p1.to_dict(),
        "django__django-11505": p2.to_dict()
    }
    with open(OUTPUT_DIR / "protocol_examples.json", "w") as f:
        json.dump(examples, f, indent=2)

    # 4. Build blocked boundary example for django-13455 (ABSTAIN_BOUNDARY_EDIT)
    p3 = ActionProtocol(
        protocol_id="p_django-13455_v0",
        protocol_type="ABSTAIN_BOUNDARY_EDIT",
        task_id="django__django-13455",
        rollback_policy="git_checkout_discard",
        verifier_required=True,
        owner_approval_required=True,
        abstain_reason="QuerySet.values requires broad SQL rewrite affecting compiler.py, query.py, and models.py. Exceeds safe 2-file/5-action budget.",
        files_involved=["django/db/models/sql/compiler.py", "django/db/models/query.py", "django/db/models/manager.py"]
    )
    blocked_examples = {
        "django__django-13455": p3.to_dict()
    }
    with open(OUTPUT_DIR / "blocked_boundary_examples.json", "w") as f:
        json.dump(blocked_examples, f, indent=2)

    print("Y2 Protocol Generator completed successfully.")


if __name__ == "__main__":
    main()
