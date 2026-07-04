import pytest
import hashlib
from nexus.services.local_heal.diff_to_ssrp import DiffToSSRPConverter

def test_diff_to_ssrp_converts_single_file_exact_preimage():
    source = (
        "def add(a, b):\n"
        "    return a + b\n"
        "def sub(a, b):\n"
        "    return a - b\n"
    )
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,4 +1,4 @@\n"
        " def add(a, b):\n"
        "-    return a + b\n"
        "+    return int(a + b)\n"
        " def sub(a, b):\n"
        "     return a - b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_to_ssrp_converted"
    assert "FILE: math.py" in ssrp
    assert "<<<<<<< SEARCH" in ssrp
    assert "return a + b" in ssrp
    assert "return int(a + b)" in ssrp
    assert ">>>>>>> REPLACE" in ssrp

def test_diff_to_ssrp_rejects_multi_file_diff():
    source = "content"
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
        "--- a/other.py\n"
        "+++ b/other.py\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_multi_file_rejected"
    assert ssrp == ""

def test_diff_to_ssrp_rejects_target_file_mismatch():
    source = "content"
    diff = (
        "--- a/other.py\n"
        "+++ b/other.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_target_mismatch"
    assert ssrp == ""

def test_diff_to_ssrp_rejects_missing_preimage():
    source = "content"
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-missing line\n"
        "+b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_missing_preimage"
    assert ssrp == ""

def test_diff_to_ssrp_rejects_ambiguous_preimage():
    source = (
        "a\n"
        "a\n"
    )
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_ambiguous_preimage"
    assert ssrp == ""

def test_diff_to_ssrp_records_source_hash():
    source = "some source content"
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-some source content\n"
        "+replaced\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_to_ssrp_converted"
    expected_src_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    expected_cand_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    assert tele["source_hash_before"] == expected_src_hash
    assert tele["candidate_hash"] == expected_cand_hash


# --- C15-5H Integration: PatchSynthesisPhase + DiffToSSRPConverter bridge ---

def test_c15_5h_patch_synthesis_phase_conversion_with_localized_file(tmp_path):
    """C15-5H: PatchSynthesisPhase.run() must reach DiffToSSRPConverter when
    localized_files is a proper List[LocalizedFile] (not raw tuple list).

    This test reproduces the exact failure: if _dr_localized_files was tuples,
    loc_file.path would throw AttributeError and model_decisions would be empty,
    causing conversion_status to remain "none" and rejection_reason to become
    "unified_diff_malformed".
    """
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.interface import PatchSynthesisInput, LocalizedFile
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
    from nexus.services.local_heal.patcher import Patcher

    # Set up the source file on disk
    buggy_source = (
        "def normalize_score(score, min_val, max_val):\n"
        "    return (score - min_val) / (max_val - min_val)\n"
    )
    target_rel = "toy/math_util.py"
    target_abs = tmp_path / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text(buggy_source, encoding="utf-8")

    # The mock LLM always returns a valid unified diff for this source
    mock_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def normalize_score(score, min_val, max_val):\n"
        "-    return (score - min_val) / (max_val - min_val)\n"
        "+    if max_val == min_val:\n"
        "+        return 0.5\n"
        "+    return (score - min_val) / (max_val - min_val)\n"
    )

    def mock_generate(system_prompt, user_prompt=None, model=None, timeout=None, options=None, api_type=None, **kwargs):
        return mock_diff

    phase = PatchSynthesisPhase(
        parser=SolidSearchReplaceProtocol(),
        patcher=Patcher(),
        ollama_generate_fn=mock_generate,
    )

    # The critical part: use LocalizedFile (not tuple)
    input_data = PatchSynthesisInput(
        instance_id="test-c15-5h",
        problem_statement="Fix normalize_score to handle division by zero",
        repro_evidence="",
        plan=None,
        localized_files=[LocalizedFile(path=target_rel, content=buggy_source)],
        repo_dir=tmp_path,
        reasoning_mode="INTUITIVE",
        attempt=1,
        max_tries=1,
    )

    output = phase.run(input_data)

    # The conversion must have been attempted (model_decisions must not be empty)
    assert len(output.model_decisions) > 0, (
        "model_decisions is empty — PatchSynthesisPhase.run() likely threw AttributeError "
        "on loc_file.path because localized_files[0] was a tuple instead of LocalizedFile."
    )

    # The last patch decision must have a conversion_status set
    last_pd = next(
        (d for d in reversed(output.model_decisions) if isinstance(d, dict) and d.get("phase") in ("patch", "semantic_retry_patch")),
        None
    )
    assert last_pd is not None, "No patch phase decision found in model_decisions"
    conv_status = last_pd.get("conversion_status", "none")

    # Converter must have been called (status != "none")
    assert conv_status != "none", (
        f"conversion_status is 'none', meaning DiffToSSRPConverter was never called. "
        f"This is the C15-5H bug: tuple in localized_files causes loc_file.path AttributeError. "
        f"Last decision: {last_pd}"
    )

    # For a valid diff with matching preimage, conversion must succeed
    assert conv_status == "unified_diff_to_ssrp_converted", (
        f"Expected unified_diff_to_ssrp_converted, got: {conv_status}. "
        f"Preimage match status: {last_pd.get('preimage_match_status')}. "
        f"Last decision: {last_pd}"
    )
