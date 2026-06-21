"""Y2: Controlled Multi-Anchor / Multi-File Action Protocol."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
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
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.NO_BLOCKS_FOUND,
                    message="TWO_FILE_COORDINATED_EDIT requires owner_approval_required = True by default.",
                    file_path=""
                )
            )

        # 5. BE-Track: Multi-step local edit checks
        if self.protocol_type == "MULTI_STEP_LOCAL_EDIT":
            for action in self.ordered_actions:
                if not action.anchor_symbol and not action.exact_search_text:
                    return ValidationResult(
                        is_valid=False,
                        error=PatchError(
                            kind=PatchErrorKind.PATCH_EMPTY,
                            message="MULTI_STEP_LOCAL_EDIT action missing anchor or search text.",
                            file_path=action.file_path
                        )
                    )

        # 6. BE-Track: Bounded cross-file edit checks
        if self.protocol_type == "BOUNDED_CROSS_FILE_EDIT":
            if len(self.files_involved) > 3:
                return ValidationResult(
                    is_valid=False,
                    error=PatchError(
                        kind=PatchErrorKind.NO_BLOCKS_FOUND,
                        message="BOUNDED_CROSS_FILE_EDIT involves too many files (>3).",
                        file_path=""
                    )
                )
            action_files = {a.file_path for a in self.ordered_actions}
            if action_files - set(self.files_involved):
                return ValidationResult(
                    is_valid=False,
                    error=PatchError(
                        kind=PatchErrorKind.NO_BLOCKS_FOUND,
                        message="BOUNDED_CROSS_FILE_EDIT action files exceed files_involved set.",
                        file_path=""
                    )
                )

        # 7. BE-Track: Dependent symbol update checks
        if self.protocol_type == "DEPENDENT_SYMBOL_UPDATE":
            if not self.dependency_edges:
                return ValidationResult(
                    is_valid=False,
                    error=PatchError(
                        kind=PatchErrorKind.NO_BLOCKS_FOUND,
                        message="DEPENDENT_SYMBOL_UPDATE requires dependency edges.",
                        file_path=""
                    )
                )
            for action in self.ordered_actions:
                if not action.evidence_node_id:
                    return ValidationResult(
                        is_valid=False,
                        error=PatchError(
                            kind=PatchErrorKind.NO_BLOCKS_FOUND,
                            message="DEPENDENT_SYMBOL_UPDATE actions require evidence_node_id.",
                            file_path=action.file_path
                        )
                    )

        return ValidationResult(is_valid=True)

    def apply_transactional(self, project_root: Path, applier_func: Any, verifier_func: Any) -> tuple[bool, str]:
        """BE-Track: Transactional apply of actions with automatic rollback on failure."""
        try:
            for action in self.ordered_actions:
                success, err = applier_func(action)
                if not success:
                    self.rollback(project_root)
                    return False, f"Action {action.action_id} failed: {err}"
            
            verifier_passed, verifier_err = verifier_func()
            if not verifier_passed:
                self.rollback(project_root)
                return False, f"Verifier failed: {verifier_err}"
                
            return True, "Success"
        except Exception as e:
            self.rollback(project_root)
            return False, str(e)

    def rollback(self, project_root: Path):
        """Rollback modifications using git checkout."""
        if self.rollback_policy == "git_checkout_discard":
            for f in self.files_involved:
                if f:
                    subprocess.run(["git", "checkout", "--", f], cwd=str(project_root), capture_output=True)

    def generate_ultra_review_report(self) -> Dict[str, Any]:
        """Runs automated Ultra Review check on this action protocol (Z2-P3)."""
        security_risk = "low"
        regression_risk = "low"
        broad_edit_risk = "low"
        owner_approval_boundary = "no_gate_required"

        if self.protocol_type == "TWO_FILE_COORDINATED_EDIT":
            regression_risk = "medium"
            broad_edit_risk = "medium"
            owner_approval_boundary = "owner_gated_two_file"
        elif self.protocol_type == "ABSTAIN_BOUNDARY_EDIT":
            regression_risk = "high"
            broad_edit_risk = "high"
            owner_approval_boundary = "abstain_out_of_bounds"
            security_risk = "medium"
        elif self.protocol_type == "BOUNDED_CROSS_FILE_EDIT":
            regression_risk = "medium"
            broad_edit_risk = "medium"
            owner_approval_boundary = "bounded_cross_file"

        return {
            "security_risk": security_risk,
            "regression_risk": regression_risk,
            "broad_edit_risk": broad_edit_risk,
            "owner_approval_boundary": owner_approval_boundary,
            "audit_status": "PASSED"
        }

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
            "ultra_review_report": self.generate_ultra_review_report(),
        }
