from nexus.delivery.interactive import (
    resolve_check_level,
    resolve_delivery_mode,
    resolve_self_heal_mode,
)


def test_resolve_delivery_mode_returns_explicit_high() -> None:
    assert resolve_delivery_mode("high", stdin_isatty=False) == "high"


def test_resolve_delivery_mode_defaults_to_standard_when_not_interactive() -> None:
    assert resolve_delivery_mode("ask", stdin_isatty=False) == "standard"


def test_resolve_delivery_mode_prompts_for_high_delivery() -> None:
    answers = iter(["y"])

    result = resolve_delivery_mode(
        "ask",
        input_func=lambda prompt: next(answers),
        stdin_isatty=True,
    )

    assert result == "high"


def test_resolve_check_level_defaults_to_standard_when_not_interactive() -> None:
    assert resolve_check_level("ask", stdin_isatty=False) == "standard"


def test_resolve_check_level_prompts_for_choice() -> None:
    answers = iter(["3"])

    result = resolve_check_level(
        "ask",
        input_func=lambda prompt: next(answers),
        stdin_isatty=True,
    )

    assert result == "high"


def test_resolve_self_heal_mode_defaults_to_dry_run_when_not_interactive() -> None:
    assert resolve_self_heal_mode("ask", stdin_isatty=False) == "dry-run"


def test_resolve_self_heal_mode_prompts_for_choice() -> None:
    answers = iter(["strict"])

    result = resolve_self_heal_mode(
        "ask",
        input_func=lambda prompt: next(answers),
        stdin_isatty=True,
    )

    assert result == "strict"
