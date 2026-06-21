"""Y2: Controlled Multi-Anchor / Multi-File Action Protocol."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from nexus.services.local_heal.protocol import ValidationResult
from nexus.services.local_heal.errors import PatchError, PatchErrorKind


@dataclass
class ProtocolAction:
    action_id: str
    file_path: str
    anchor_symbol: str
    exact_search_text: str
    replacement_text: str
    evidence_node_id: Optional[str] = None

    def validate(self) -> ValidationResult:
        if not self.file_path or not self.anchor_symbol:
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.PATCH_EMPTY,
                    message=f"Action {self.action_id} missing file path or anchor symbol.",
                    file_path=self.file_path
                )
            )
        if not self.exact_search_text or not self.replacement_text:
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.PATCH_EMPTY,
                    message=f"Action {self.action_id} has empty search or replacement text.",
                    file_path=self.file_path
                )
            )
        return ValidationResult(is_valid=True)


@dataclass
class ActionDependency:
    source_action_id: str
    target_action_id: str
    dependency_reason: str = ""


@dataclass
class ActionProtocol:
    protocol_id: str
    protocol_type: str  # MULTI_ANCHOR_SEQUENCE, TWO_FILE_COORDINATED_EDIT, etc.
    task_id: str
    ordered_actions: List[ProtocolAction] = field(default_factory=list)
    dependency_edges: List[ActionDependency] = field(default_factory=list)
    rollback_policy: str = "git_checkout_discard"
    verifier_required: bool = True
    owner_approval_required: bool = False
    abstain_reason: Optional[str] = None
    files_involved: List[str] = field(default_factory=list)

    def validate_protocol(self) -> ValidationResult:
        # 1. Abstain Check
        if self.protocol_type == "ABSTAIN_BOUNDARY_EDIT":
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.NO_BLOCKS_FOUND,
                    message=f"Abstain due to hard boundary edit: {self.abstain_reason or 'No reason provided'}",
                    file_path=""
                )
            )

        # 2. Check each action individually
        for action in self.ordered_actions:
            res = action.validate()
            if not res.is_valid:
                return res

        # 3. Check verifier requirements
        if self.verifier_required and not self.ordered_actions:
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.PATCH_EMPTY,
                    message="Protocol demands verifier but has no actions to apply.",
                    file_path=""
                )
            )

        # 4. Check owner approval constraints for TWO_FILE_COORDINATED_EDIT
        if self.protocol_type == "TWO_FILE_COORDINATED_EDIT" and not self.owner_approval_required:
            # We enforce that coordinated 2-file edits MUST have owner approval flag enabled by default
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.NO_BLOCKS_FOUND,
                    message="TWO_FILE_COORDINATED_EDIT requires owner_approval_required = True by default.",
                    file_path=""
                )
            )

        return ValidationResult(is_valid=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_type": self.protocol_type,
            "task_id": self.task_id,
            "ordered_actions": [
                {
                    "action_id": a.action_id,
                    "file_path": a.file_path,
                    "anchor_symbol": a.anchor_symbol,
                    "exact_search_text": a.exact_search_text,
                    "replacement_text": a.replacement_text,
                    "evidence_node_id": a.evidence_node_id,
                }
                for a in self.ordered_actions
            ],
            "dependency_edges": [
                {
                    "source_action_id": d.source_action_id,
                    "target_action_id": d.target_action_id,
                    "dependency_reason": d.dependency_reason,
                }
                for d in self.dependency_edges
            ],
            "rollback_policy": self.rollback_policy,
            "verifier_required": self.verifier_required,
            "owner_approval_required": self.owner_approval_required,
            "abstain_reason": self.abstain_reason,
            "files_involved": self.files_involved,
        }
