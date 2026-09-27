"""Unit tests for Apple FM Candidate Adapter in Provider Adoption Framework."""

import subprocess
from unittest.mock import patch

from nexus.calibration.provider_adoption.apple_fm_adapter import (
    AppleFMCandidateAdapter,
)
from nexus.calibration.provider_adoption.capability import (
    CAP_001_PLAIN_TEXT,
    CAP_004_CLASSIFICATION,
    CAP_005_EXTRACTION,
    CapabilityStatus,
)


def test_apple_fm_license_agreed_allows_environment():
    adapter = AppleFMCandidateAdapter("/usr/bin/fm")
    mock_res = subprocess.CompletedProcess(
        args=["/usr/bin/fm", "license", "--status"],
        returncode=0,
        stdout="Agreed.",
        stderr="",
    )
    with patch("platform.system", return_value="Darwin"):
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                blocked, reason = adapter.is_environment_blocked()
                assert blocked is False
                assert reason == ""


def test_apple_fm_offline_honesty_invariant_6_1():
    """Verify that Apple FM physical identity does not fake VERIFIED_OFFLINE."""
    adapter = AppleFMCandidateAdapter()
    ident = adapter.inspect_identity()
    # Invariant 6.1: must be UNKNOWN until physical offline execution is proved
    assert ident.offline_availability == "UNKNOWN"
    assert ident.network_dependency == "UNKNOWN"


def test_apple_fm_mocked_blocked_license_response():
    """Verify mock simulation of license agreement failure on non-macOS or CI."""
    adapter = AppleFMCandidateAdapter("/usr/bin/fm")
    mock_res = subprocess.CompletedProcess(
        args=["/usr/bin/fm", "license", "--status"],
        returncode=69,
        stdout="",
        stderr="Not agreed. Run 'sudo fm license' to review and agree.",
    )
    with patch("platform.system", return_value="Darwin"):
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                blocked, reason = adapter.is_environment_blocked()
                assert blocked is True
                assert "APPLE_FM_LICENSE_NOT_AGREED" in reason

                probe = adapter.probe_capability(CAP_001_PLAIN_TEXT)
                assert probe.status == CapabilityStatus.BLOCKED
                assert probe.exit_code == 69


def test_apple_fm_uses_respond_command_contract():
    """Verify Apple FM adapter strictly uses 'respond' command and not 'prompt'."""
    adapter = AppleFMCandidateAdapter("/usr/bin/fm")
    mock_license_ok = subprocess.CompletedProcess(
        args=["/usr/bin/fm", "license", "--status"],
        returncode=0,
        stdout="Agreed.",
        stderr="",
    )
    mock_respond_ok = subprocess.CompletedProcess(
        args=[
            "/usr/bin/fm",
            "respond",
            "--no-stream",
            "--greedy",
            "Reply with exactly OK and no other text.",
        ],
        returncode=0,
        stdout="OK",
        stderr="",
    )

    calls = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if "license" in cmd:
            return mock_license_ok
        return mock_respond_ok

    with patch("platform.system", return_value="Darwin"):
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run", side_effect=mock_subprocess_run):
                probe = adapter.probe_capability(CAP_001_PLAIN_TEXT)
                assert probe.status == CapabilityStatus.SUPPORTED

                # Check all command calls made
                for c in calls:
                    assert "prompt" not in c, f"Contract violation: 'prompt' found in CLI call: {c}"
                assert any(c[:2] == ["/usr/bin/fm", "respond"] for c in calls)
                assert any("--no-stream" in c and "--greedy" in c for c in calls if "respond" in c)


def test_apple_fm_classification_and_extraction_probes_require_exact_semantics():
    adapter = AppleFMCandidateAdapter("/usr/bin/fm")
    mock_license_ok = subprocess.CompletedProcess(
        args=["/usr/bin/fm", "license", "--status"],
        returncode=0,
        stdout="Agreed.",
        stderr="",
    )

    def mock_subprocess_run(cmd, *args, **kwargs):
        if "license" in cmd:
            return mock_license_ok
        prompt = cmd[-1]
        if "sentiment" in prompt:
            output = "POSITIVE"
        elif "error code" in prompt:
            output = "137"
        else:
            output = "unexpected"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=output, stderr="")

    with patch("platform.system", return_value="Darwin"):
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run", side_effect=mock_subprocess_run):
                cls_probe = adapter.probe_capability(CAP_004_CLASSIFICATION)
                ext_probe = adapter.probe_capability(CAP_005_EXTRACTION)

    assert cls_probe.status == CapabilityStatus.SUPPORTED
    assert cls_probe.raw_output == "POSITIVE"
    assert ext_probe.status == CapabilityStatus.SUPPORTED
    assert ext_probe.raw_output == "137"


def test_apple_fm_execute_case_uses_respond_command_contract():
    """Verify Apple FM adapter execute_case strictly calls 'respond' and not 'prompt'."""
    from nexus.calibration.provider_adoption.cohort import CohortCase

    adapter = AppleFMCandidateAdapter("/usr/bin/fm")
    mock_license_ok = subprocess.CompletedProcess(
        args=["/usr/bin/fm", "license", "--status"],
        returncode=0,
        stdout="Agreed.",
        stderr="",
    )
    mock_respond_ok = subprocess.CompletedProcess(
        args=["/usr/bin/fm", "respond", "Classify this prompt"],
        returncode=0,
        stdout="classification_result",
        stderr="",
    )

    calls = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if "license" in cmd:
            return mock_license_ok
        return mock_respond_ok

    case = CohortCase("C1", "classification", "Classify this prompt", "classification_result")

    with patch("platform.system", return_value="Darwin"):
        with patch("os.path.isfile", return_value=True):
            with patch("subprocess.run", side_effect=mock_subprocess_run):
                out, valid, err, lat = adapter.execute_case(case)
                assert valid is True
                assert out == "classification_result"
                assert err is None
                assert lat >= 0

                for c in calls:
                    assert "prompt" not in c, f"Contract violation: 'prompt' found in CLI call: {c}"
                assert ["/usr/bin/fm", "respond", "Classify this prompt"] in calls


def test_apple_fm_declares_physical_ceiling_without_running_license_or_benchmark():
    """Verify AppleFMAdapter declares PHYSICAL ceiling without running CLI, license checks, or benchmarks."""
    from nexus.calibration.provider_adoption.adapter import get_adapter_evidence_ceiling
    from nexus.calibration.provider_adoption.cohort import EvidenceLevel

    with patch("subprocess.run") as mock_run:
        adapter = AppleFMCandidateAdapter("/usr/bin/fm")
        assert adapter.max_evidence_level == EvidenceLevel.PHYSICAL
        assert get_adapter_evidence_ceiling(adapter) == EvidenceLevel.PHYSICAL
        # Subprocess must NOT have been called merely by inspecting the evidence ceiling
        mock_run.assert_not_called()
