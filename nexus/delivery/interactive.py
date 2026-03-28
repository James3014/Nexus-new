from __future__ import annotations

import sys
from typing import Callable


def resolve_delivery_mode(
    requested_mode: str,
    input_func: Callable[[str], str] = input,
    stdin_isatty: bool | None = None,
) -> str:
    if requested_mode in {"standard", "high"}:
        return requested_mode

    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    if not interactive:
        return "standard"

    answer = input_func("啟用高標交付模式？這會強制驗證後才能交付 [y/N]: ")
    return "high" if answer.strip().lower() in {"y", "yes"} else "standard"


def resolve_check_level(
    requested_level: str,
    input_func: Callable[[str], str] = input,
    stdin_isatty: bool | None = None,
) -> str:
    if requested_level in {"quick", "standard", "high", "full", "pre-merge", "nightly"}:
        return requested_level

    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    if not interactive:
        return "standard"

    answer = input_func(
        "選擇自檢強度 [1=quick, 2=standard, 3=high, 4=full] (預設 2): "
    ).strip().lower()
    mapping = {
        "1": "quick",
        "quick": "quick",
        "2": "standard",
        "standard": "standard",
        "3": "high",
        "high": "high",
        "4": "full",
        "full": "full",
        "": "standard",
    }
    return mapping.get(answer, "standard")


def resolve_self_heal_mode(
    requested_mode: str,
    input_func: Callable[[str], str] = input,
    stdin_isatty: bool | None = None,
) -> str:
    if requested_mode in {"dry-run", "standard", "strict"}:
        return requested_mode

    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    if not interactive:
        return "dry-run"

    answer = input_func(
        "選擇自癒模式 [1=dry-run, 2=standard, 3=strict] (預設 1): "
    ).strip().lower()
    mapping = {
        "1": "dry-run",
        "dry-run": "dry-run",
        "dry": "dry-run",
        "2": "standard",
        "standard": "standard",
        "3": "strict",
        "strict": "strict",
        "": "dry-run",
    }
    return mapping.get(answer, "dry-run")
