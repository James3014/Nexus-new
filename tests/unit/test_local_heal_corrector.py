from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.errors import PatchError, PatchErrorKind


def test_corrector_distinguishes_visible_test_failure_from_no_logic_change():
    corrector = SelfCorrector()
    error = PatchError(
        kind=PatchErrorKind.NO_EFFECTIVE_CODE_CHANGE,
        message=(
            "Tests failed:\n"
            "Expected matrix:\n"
            "[[ True False]]\n"
            "Actual matrix:\n"
            "[[ True  True]]\n"
        ),
    )

    prompt = corrector.build_retry_prompt("Original prompt", error)

    assert "previous patch compiled and changed code" in prompt
    assert "visible verification still failed" in prompt
    assert "Compare the expected and actual outputs" in prompt
    assert "only modified docstrings" not in prompt


def test_corrector_keeps_no_logic_change_warning_for_static_no_effective_change():
    corrector = SelfCorrector()
    error = PatchError(
        kind=PatchErrorKind.NO_EFFECTIVE_CODE_CHANGE,
        message="Only comments or formatting changed.",
    )

    prompt = corrector.build_retry_prompt("Original prompt", error)

    assert "only modified docstrings" in prompt
    assert "visible verification still failed" not in prompt
