from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

import click


P = ParamSpec("P")
T = TypeVar("T")


class NexusCliActionError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = int(exit_code)


def translate_action_exceptions(action: Callable[P, T]) -> Callable[P, T]:
    @wraps(action)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return action(*args, **kwargs)
        except (KeyboardInterrupt, SystemExit, click.Abort):
            raise
        except NexusCliActionError as exc:
            click_exc = click.ClickException(str(exc))
            click_exc.exit_code = exc.exit_code
            raise click_exc from exc

    return wrapper
