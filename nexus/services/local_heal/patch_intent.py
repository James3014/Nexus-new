"""PatchIntent parser and validator for line-span patch protocol."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json


class PatchIntentErrorKind(Enum):
    PATCH_INTENT_INVALID = "PATCH_INTENT_INVALID"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FIELD_TYPE = "INVALID_FIELD_TYPE"
    INVALID_SPAN = "INVALID_SPAN"
    INVALID_FALLBACK_STRATEGY = "INVALID_FALLBACK_STRATEGY"
    EMPTY_REPLACEMENT = "EMPTY_REPLACEMENT"
    INVALID_PATH = "INVALID_PATH"


ALLOWED_FALLBACK_STRATEGIES = {"reject", "expand_span", "ask_retry"}

REQUIRED_FIELDS = {
    "file_path": str,
    "span_start": int,
    "span_end": int,
    "original_hash": str,
    "replacement": str,
    "fallback_strategy": str,
}


@dataclass
class PatchIntent:
    file_path: str
    symbol_name: Optional[str]
    span_start: int
    span_end: int
    original_hash: str
    replacement: str
    expected_ast_valid: bool
    fallback_strategy: str


@dataclass
class PatchIntentError:
    kind: PatchIntentErrorKind
    message: str
    field: Optional[str] = None


def _validate_path(path: str) -> Optional[PatchIntentError]:
    if not isinstance(path, str):
        return PatchIntentError(PatchIntentErrorKind.INVALID_FIELD_TYPE, f"file_path must be str, got {type(path).__name__}", "file_path")
    if not path:
        return PatchIntentError(PatchIntentErrorKind.MISSING_FIELD, "file_path is empty", "file_path")
    if path.startswith("/"):
        return PatchIntentError(PatchIntentErrorKind.INVALID_PATH, f"file_path must be relative: {path}", "file_path")
    if ".." in path:
        return PatchIntentError(PatchIntentErrorKind.INVALID_PATH, f"file_path must not contain '..': {path}", "file_path")
    return None


def _validate_span(start: int, end: int) -> Optional[PatchIntentError]:
    if not isinstance(start, int) or not isinstance(end, int):
        return PatchIntentError(PatchIntentErrorKind.INVALID_FIELD_TYPE, "span_start/span_end must be int", "span")
    if start < 1 or end < 1:
        return PatchIntentError(PatchIntentErrorKind.INVALID_SPAN, f"span must be positive: {start}-{end}", "span")
    if start > end:
        return PatchIntentError(PatchIntentErrorKind.INVALID_SPAN, f"span_start > span_end: {start} > {end}", "span")
    return None


def parse_patch_intent(payload: dict) -> PatchIntent | PatchIntentError:
    if not isinstance(payload, dict):
        return PatchIntentError(PatchIntentErrorKind.PATCH_INTENT_INVALID, "payload must be dict")

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in payload:
            return PatchIntentError(PatchIntentErrorKind.MISSING_FIELD, f"missing field: {field}", field)
        if not isinstance(payload[field], expected_type):
            return PatchIntentError(PatchIntentErrorKind.INVALID_FIELD_TYPE, f"{field} must be {expected_type.__name__}, got {type(payload[field]).__name__}", field)

    err = _validate_path(payload["file_path"])
    if err:
        return err

    err = _validate_span(payload["span_start"], payload["span_end"])
    if err:
        return err

    if not payload["original_hash"]:
        return PatchIntentError(PatchIntentErrorKind.MISSING_FIELD, "original_hash is empty", "original_hash")

    if not payload["replacement"]:
        return PatchIntentError(PatchIntentErrorKind.EMPTY_REPLACEMENT, "replacement is empty", "replacement")

    if payload["fallback_strategy"] not in ALLOWED_FALLBACK_STRATEGIES:
        return PatchIntentError(PatchIntentErrorKind.INVALID_FALLBACK_STRATEGY, f"invalid fallback_strategy: {payload['fallback_strategy']}", "fallback_strategy")

    return PatchIntent(
        file_path=payload["file_path"],
        symbol_name=payload.get("symbol_name"),
        span_start=payload["span_start"],
        span_end=payload["span_end"],
        original_hash=payload["original_hash"],
        replacement=payload["replacement"],
        expected_ast_valid=payload.get("expected_ast_valid", True),
        fallback_strategy=payload["fallback_strategy"],
    )


def validate_patch_intent(intent: PatchIntent) -> list[PatchIntentError]:
    errors = []
    err = _validate_path(intent.file_path)
    if err:
        errors.append(err)
    err = _validate_span(intent.span_start, intent.span_end)
    if err:
        errors.append(err)
    if not intent.original_hash:
        errors.append(PatchIntentError(PatchIntentErrorKind.MISSING_FIELD, "original_hash is empty", "original_hash"))
    if not intent.replacement:
        errors.append(PatchIntentError(PatchIntentErrorKind.EMPTY_REPLACEMENT, "replacement is empty", "replacement"))
    if intent.fallback_strategy not in ALLOWED_FALLBACK_STRATEGIES:
        errors.append(PatchIntentError(PatchIntentErrorKind.INVALID_FALLBACK_STRATEGY, f"invalid: {intent.fallback_strategy}", "fallback_strategy"))
    return errors
