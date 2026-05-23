from __future__ import annotations

import click
import pytest

from scripts.engine.commands.exception_translation import (
    NexusCliActionError,
    translate_action_exceptions,
)


def test_translate_action_exceptions_preserves_success_value():
    @translate_action_exceptions
    def action() -> str:
        return "ok"

    assert action() == "ok"


def test_translate_action_exceptions_turns_domain_error_into_click_exception():
    @translate_action_exceptions
    def action() -> None:
        raise NexusCliActionError("invalid action state", exit_code=7)

    with pytest.raises(click.ClickException) as exc_info:
        action()

    assert str(exc_info.value) == "invalid action state"
    assert exc_info.value.exit_code == 7


def test_translate_action_exceptions_passes_keyboard_interrupt_through():
    @translate_action_exceptions
    def action() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        action()


def test_translate_action_exceptions_passes_click_abort_through():
    @translate_action_exceptions
    def action() -> None:
        raise click.Abort

    with pytest.raises(click.Abort):
        action()


def test_translate_action_exceptions_passes_system_exit_through():
    @translate_action_exceptions
    def action() -> None:
        raise SystemExit(130)

    with pytest.raises(SystemExit) as exc_info:
        action()

    assert exc_info.value.code == 130
