import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple
from pathlib import Path
from nexus.services.local_heal.interface import LocalizedFile
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, PatchIntent

@dataclass
class CandidatePatch:
    candidate_id: str
    model: str
    model_call_id: str
    prompt_variant: str
    replacement_text: str
    replacement_text_hash: str
    patch_apply_status: str = "pending" # pending, applied, failed
    verifier_status: str = "skipped" # skipped, passed, failed
    compliance_status: str = "skipped" # skipped, passed, failed
    failure_stage: str = "none" # parse_fail, apply_fail, verifier_fail, compliance_fail
    selected: bool = False

class CandidatePatchSearcher:
    """
    🛡️ Candidate Patch Search Engine (P3)
    Generates N replacement candidates and selects using deterministic filter chains.
    """
    def __init__(self, parser: SolidSearchReplaceProtocol, patch_applier: Any, verifier: Any = None):
        self.parser = parser
        self.patch_applier = patch_applier
        self.verifier = verifier

    def search_best_candidate(
        self,
        raw_outputs: List[Tuple[str, str, str]], # [(raw_output, prompt_variant, call_id)]
        anchor_text: str,
        repo_dir: Path,
        localized_files: List[LocalizedFile],
        model: str,
        compliance_checker: Any = None
    ) -> Tuple[CandidatePatch | None, List[CandidatePatch]]:
        candidates: List[CandidatePatch] = []
        seen_hashes = set()

        for idx, (raw_out, variant, call_id) in enumerate(raw_outputs):
            candidate_id = f"cand_{idx + 1}"
            
            # 1. Parse candidate
            intents_or_error = self.parser.parse(raw_out, anchor_text=anchor_text)
            if isinstance(intents_or_error, PatchError):
                candidates.append(CandidatePatch(
                    candidate_id=candidate_id,
                    model=model,
                    model_call_id=call_id,
                    prompt_variant=variant,
                    replacement_text="",
                    replacement_text_hash="",
                    patch_apply_status="failed",
                    failure_stage="parse_fail"
                ))
                continue

            # Assuming single-intent patch for search task
            intent = intents_or_error[0]
            rep_text = intent.replace
            rep_hash = hashlib.sha256(rep_text.strip().encode()).hexdigest()[:16]

            # 2. Reject duplicate candidates
            if rep_hash in seen_hashes:
                # Duplicate is discarded
                continue
            seen_hashes.add(rep_hash)

            candidate = CandidatePatch(
                candidate_id=candidate_id,
                model=model,
                model_call_id=call_id,
                prompt_variant=variant,
                replacement_text=rep_text,
                replacement_text_hash=rep_hash
            )

            # 3. Apply patch
            apply_res = self.patch_applier.apply_and_validate(
                intents=[intent],
                repo_dir=repo_dir,
                localized_files=localized_files
            )

            if not apply_res.success:
                candidate.patch_apply_status = "failed"
                candidate.failure_stage = "apply_fail"
                candidates.append(candidate)
                continue

            candidate.patch_apply_status = "applied"

            # 4. Run verifier (Verifier gate)
            if self.verifier:
                v_success, v_report = self.verifier.run_verification(repo_dir)
                candidate.verifier_status = "passed" if v_success else "failed"
                if not v_success:
                    candidate.failure_stage = "verifier_fail"
                    # Restore file for next candidate
                    self._restore_files(repo_dir, intents_or_error)
                    candidates.append(candidate)
                    continue
            else:
                # No verifier available — success cannot occur without verifier
                candidate.failure_stage = "verifier_fail"
                self._restore_files(repo_dir, intents_or_error)
                candidates.append(candidate)
                continue

            # 5. Run compliance checker (Compliance gate)
            if compliance_checker:
                # We mock or run compliance check on receipt data
                comp_result = compliance_checker.check_compliance(intent, apply_res)
                candidate.compliance_status = "passed" if comp_result.is_pass else "failed"
                if not comp_result.is_pass:
                    candidate.failure_stage = "compliance_fail"
                    self._restore_files(repo_dir, intents_or_error)
                    candidates.append(candidate)
                    continue
            else:
                candidate.compliance_status = "passed"

            # 6. Candidate is fully valid
            candidate.selected = True
            candidates.append(candidate)
            
            # Found first verifier-backed compliant candidate — return immediately
            return candidate, candidates

        # If none of the candidates passed, return None
        return None, candidates

    def _restore_files(self, repo_dir: Path, intents: List[PatchIntent]):
        # Helper to restore workspace files
        import subprocess
        for intent in intents:
            target_path = repo_dir / intent.file_path
            if target_path.exists():
                subprocess.run(["git", "checkout", "--", str(target_path)], cwd=str(repo_dir), capture_output=True)
