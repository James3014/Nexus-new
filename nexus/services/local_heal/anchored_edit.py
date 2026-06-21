import hashlib
from dataclasses import dataclass, field
from nexus.services.local_heal.errors import MatchAuthority, PatchError, PatchErrorKind
from nexus.services.local_heal.protocol import ValidationResult

@dataclass
class AnchoredEdit:
    """
    🛡️ Control-Plane Anchored Edit Data Structure (P2 + P9 hardening)
    Nexus supplies the exact source anchor; the model supplies the replacement content.
    """
    file_path: str
    source_git_sha: str
    source_hash: str
    anchor_id: str
    start_line: int
    end_line: int
    symbol_name: str
    exact_source_text: str
    replacement_text: str
    replacement_supplied_by: str = "model"
    search_supplied_by: str = "control_plane"
    protocol_mode: str = "anchored_edit"
    model_generated_search: bool = False
    # P9: anchor provenance metadata
    base_commit: str = ""
    checked_out_commit: str = ""
    anchor_extraction_stage: str = "unknown"  # "after_base_checkout" or "unknown"
    anchor_text_hash: str = ""
    source_hash_before: str = ""
    source_hash_after: str = ""
    anchor_count: int = 0

    def validate(self, current_source_text: str) -> ValidationResult:
        # 1. Reject stale source hash
        current_hash = hashlib.sha256(current_source_text.encode()).hexdigest()[:16]
        if current_hash != self.source_hash:
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.SOURCE_STALE,
                    message=f"Stale source hash: expected {self.source_hash}, got {current_hash}",
                    file_path=self.file_path
                )
            )

        # 2. Reject empty replacement
        if not self.replacement_text or not self.replacement_text.strip():
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.PATCH_EMPTY,
                    message="Replacement text is empty.",
                    file_path=self.file_path
                )
            )

        # 3. Ensure exact_source_text is in current_source_text
        if self.exact_source_text not in current_source_text:
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.ANCHOR_NOT_IN_BASE_SOURCE,
                    message="Exact source anchor not found in target file.",
                    file_path=self.file_path
                )
            )

        # 4. Check if exact_source_text appears multiple times to prevent ambiguity
        occurrences = current_source_text.count(self.exact_source_text)
        if occurrences > 1:
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.ANCHOR_AMBIGUOUS,
                    message=f"Ambiguous anchor: found {occurrences} occurrences of anchor text.",
                    file_path=self.file_path
                )
            )

        # 5. P9: Reject if anchor extraction did not happen after base_commit checkout
        if self.anchor_extraction_stage != "after_base_checkout":
            return ValidationResult(
                is_valid=False,
                error=PatchError(
                    kind=PatchErrorKind.ANCHOR_NOT_IN_BASE_SOURCE,
                    message=f"Anchor extraction stage is '{self.anchor_extraction_stage}', expected 'after_base_checkout'.",
                    file_path=self.file_path
                )
            )

        # 6. P9: Reject if source_hash changed between extraction and apply
        if self.source_hash_before and self.source_hash_after:
            if self.source_hash_before != self.source_hash_after:
                return ValidationResult(
                    is_valid=False,
                    error=PatchError(
                        kind=PatchErrorKind.SOURCE_HASH_CHANGED_AFTER_CHECKOUT,
                        message=f"Source hash changed: before={self.source_hash_before}, after={self.source_hash_after}",
                        file_path=self.file_path
                    )
                )

        # 7. P9: Reject if anchor_text_hash doesn't match the actual anchor
        if self.anchor_text_hash:
            actual_hash = hashlib.sha256(self.exact_source_text.encode()).hexdigest()[:16]
            if actual_hash != self.anchor_text_hash:
                return ValidationResult(
                    is_valid=False,
                    error=PatchError(
                        kind=PatchErrorKind.SOURCE_HASH_CHANGED_AFTER_CHECKOUT,
                        message=f"Anchor text hash mismatch: expected {self.anchor_text_hash}, got {actual_hash}",
                        file_path=self.file_path
                    )
                )

        # Everything is valid
        telemetry = {
            "source_hash": self.source_hash,
            "anchor_id": self.anchor_id,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol_name": self.symbol_name,
            "model_generated_search": self.model_generated_search,
            "match_authority": MatchAuthority.CONTROL_PLANE_VERBATIM,
            "protocol_mode": self.protocol_mode,
            "anchor_extraction_stage": self.anchor_extraction_stage,
            "anchor_text_hash": self.anchor_text_hash or hashlib.sha256(self.exact_source_text.encode()).hexdigest()[:16],
            "base_commit": self.base_commit,
            "checked_out_commit": self.checked_out_commit,
            "anchor_count": occurrences,
        }
        return ValidationResult(is_valid=True, telemetry=telemetry)
