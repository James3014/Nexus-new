import pytest
from pathlib import Path
from nexus.services.local_heal.candidate_search import CandidatePatchSearcher, CandidatePatch
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, PatchIntent
from nexus.services.local_heal.interface import LocalizedFile
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.runbook_compliance import ComplianceResult

# Stub PatchApplier
class StubPatchApplier:
    def __init__(self, success: bool = True):
        self.success = success

    def apply_and_validate(self, intents, repo_dir, localized_files):
        class ApplyResult:
            def __init__(self, succ):
                self.success = succ
                self.applied_diffs = ["diff"]
        return ApplyResult(self.success)

# Stub Verifier
class StubVerifier:
    def __init__(self, success: bool = True):
        self.success = success

    def run_verification(self, repo_dir):
        return self.success, "log"

# Stub Compliance Checker
class StubComplianceChecker:
    def __init__(self, is_pass: bool = True):
        self.is_pass = is_pass

    def check_compliance(self, intent, apply_res):
        return ComplianceResult(compliance_status="COMPLIANCE_PASS" if self.is_pass else "FAILED")


def test_candidate_search_first_success(tmp_path):
    parser = SolidSearchReplaceProtocol()
    applier = StubPatchApplier(success=True)
    verifier = StubVerifier(success=True)
    
    searcher = CandidatePatchSearcher(parser, applier, verifier)
    
    # 3 個 candidates：第一個 apply 失敗，第二個 verifier 成功，第三個 duplicate
    raw_outputs = [
        ("FILE: math.py\n<<<<<<< SEARCH\nanchor\n=======\nfailed_apply\n>>>>>>> REPLACE", "v1", "call1"),
        ("FILE: math.py\n<<<<<<< SEARCH\nanchor\n=======\nsuccess_verify\n>>>>>>> REPLACE", "v2", "call2"),
        ("FILE: math.py\n<<<<<<< SEARCH\nanchor\n=======\nsuccess_verify\n>>>>>>> REPLACE", "v3", "call3") # duplicate
    ]
    
    # 模擬第一個 candidate 的 apply 失敗
    class DynamicApplier:
        def apply_and_validate(self, intents, repo_dir, localized_files):
            class Res:
                def __init__(self, succ):
                    self.success = succ
            # 如果是 failed_apply 則返回 success=False
            return Res(intents[0].replace != "failed_apply")
            
    searcher.patch_applier = DynamicApplier()
    
    selected, candidates = searcher.search_best_candidate(
        raw_outputs=raw_outputs,
        anchor_text="anchor",
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="math.py", content="anchor")],
        model="7b"
    )
    
    # 驗證
    assert selected is not None
    assert selected.candidate_id == "cand_2"
    assert selected.replacement_text == "success_verify"
    
    # 去重驗證：第 3 個是重覆的，因此 candidates 長度應該只有 2 (或者是 candidate 3 被跳過不計入 candidates)
    # 根據我們 candidate_search.py 中的實作：if rep_hash in seen_hashes: continue。所以 candidates 裡不會有第 3 個。
    assert len(candidates) == 2
    assert candidates[0].failure_stage == "apply_fail"
    assert candidates[1].selected is True


def test_candidate_search_compliance_blocking(tmp_path):
    parser = SolidSearchReplaceProtocol()
    applier = StubPatchApplier(success=True)
    verifier = StubVerifier(success=True)
    compliance = StubComplianceChecker(is_pass=False) # compliance failed
    
    searcher = CandidatePatchSearcher(parser, applier, verifier)
    
    raw_outputs = [
        ("FILE: math.py\n<<<<<<< SEARCH\nanchor\n=======\nval\n>>>>>>> REPLACE", "v1", "call1")
    ]
    
    selected, candidates = searcher.search_best_candidate(
        raw_outputs=raw_outputs,
        anchor_text="anchor",
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="math.py", content="anchor")],
        model="7b",
        compliance_checker=compliance
    )
    
    assert selected is None
    assert len(candidates) == 1
    assert candidates[0].failure_stage == "compliance_fail"
    assert candidates[0].selected is False


def test_candidate_search_no_verifier_blocks_success(tmp_path):
    parser = SolidSearchReplaceProtocol()
    applier = StubPatchApplier(success=True)
    
    searcher = CandidatePatchSearcher(parser, applier, verifier=None) # NO verifier
    
    raw_outputs = [
        ("FILE: math.py\n<<<<<<< SEARCH\nanchor\n=======\nval\n>>>>>>> REPLACE", "v1", "call1")
    ]
    
    selected, candidates = searcher.search_best_candidate(
        raw_outputs=raw_outputs,
        anchor_text="anchor",
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="math.py", content="anchor")],
        model="7b"
    )
    
    assert selected is None
    assert len(candidates) == 1
    assert candidates[0].failure_stage == "verifier_fail"
    assert candidates[0].selected is False
