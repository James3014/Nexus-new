import hashlib
from dataclasses import dataclass
from nexus.services.local_heal.errors import MatchAuthority, PatchError, PatchErrorKind
from nexus.services.local_heal.protocol import ValidationResult

@dataclass
class AnchoredEdit:
    """
    🛡️ Control-Plane Anchored Edit Data Structure (P2)
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
                    kind=PatchErrorKind.SEARCH_MISMATCH,
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
                    kind=PatchErrorKind.NAME_SANITY_ERROR,
                    message=f"Ambiguous anchor: found {occurrences} occurrences of anchor text.",
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
            "protocol_mode": self.protocol_mode
        }
        return ValidationResult(is_valid=True, telemetry=telemetry)
