import inspect

import pytest

from nexus.pilot_cli.gateway import _coerce_long_gemini_answer
from nexus.pilot_cli.gemini_client import coerce_long_gemini_answer
from nexus.pilot_cli.session import PilotSession


@pytest.mark.parametrize(
    ("raw_text", "finish_reason"),
    [
        ("short answer", "STOP"),
        ("這是一段沒有 JSON 的長回答", "MAX_TOKENS"),
        ("", "STOP"),
    ],
    ids=["stop-plain-text", "max-tokens-no-json", "empty-text"],
)
def test_coerce_wrapper_returns_raw_text_without_raising(raw_text, finish_reason):
    session = PilotSession(provider="Gemini", model="gemini-2.5-flash", api_key="k")
    err = None
    result = None
    try:
        result = _coerce_long_gemini_answer(
            session=session,
            user_request="x" * 1200,
            raw_text=raw_text,
            finish_reason=finish_reason,
        )
    except TypeError as exc:
        err = exc
    assert err is None, f"wrapper raised: {err}"
    assert result == raw_text


def test_coerce_wrapper_signature_matches_client():
    wrapper_sig = inspect.signature(_coerce_long_gemini_answer)
    client_sig = inspect.signature(coerce_long_gemini_answer)
    assert list(wrapper_sig.parameters.keys()) == list(client_sig.parameters.keys())
    assert "second_pass_fn" not in wrapper_sig.parameters


def test_coerce_wrapper_rejects_removed_second_pass_argument():
    session = PilotSession(provider="Gemini", model="gemini-2.5-flash", api_key="k")
    raw_text = "test output"
    err = None
    result = None
    try:
        result = _coerce_long_gemini_answer(
            session=session,
            user_request="x" * 1200,
            raw_text=raw_text,
            finish_reason="STOP",
        )
    except TypeError as exc:
        err = exc
    assert err is None, f"wrapper raised: {err}"
    assert result == raw_text

    with pytest.raises(TypeError):
        _coerce_long_gemini_answer(
            session=session,
            user_request="x" * 1200,
            raw_text=raw_text,
            finish_reason="STOP",
            second_pass_fn=None,
        )
