"""Opt-in consumer for the `research:meta-opt` report's `selected_preset`.

Disabled unless ``NEXUS_APPLY_META_OPT_PRESET`` is truthy. When enabled and the
report is a measured ``status == "ok"`` report with a selected preset, the
preset's known keys override the matching ``research:auto-flow`` settings.
Everything else leaves the settings untouched and records a reason.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

APPLY_ENV_FLAG = "NEXUS_APPLY_META_OPT_PRESET"
REPORT_ENV_VAR = "NEXUS_META_OPT_REPORT"
DEFAULT_REPORT = ".nexus/reports/research/meta-opt-report.json"

# preset key -> (auto-flow setting name, "int" | "float")
PRESET_KEY_MAP: dict[str, tuple[str, str]] = {
    "timeout_sec": ("timeout_sec", "int"),
    "stage1_timeout_sec": ("stage1_timeout_sec", "int"),
    "max_time_ratio_guard": ("max_time_ratio_guard", "float"),
    "baseline_fast_sec": ("baseline_fast_sec", "float"),
    "history_window": ("history_window", "int"),
    "history_fail_threshold": ("history_fail_threshold", "int"),
    "dynamic_timeout_multiplier": ("dynamic_timeout_multiplier", "float"),
    "min_dynamic_stage1_timeout": ("min_dynamic_stage1_timeout", "int"),
}


def meta_opt_preset_enabled(env: Mapping[str, str] | None = None) -> bool:
    value = (env if env is not None else os.environ).get(APPLY_ENV_FLAG, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce(value: Any, kind: str) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if kind == "int":
        if isinstance(value, float) and not value.is_integer():
            return None
        number: int | float = int(value)
    else:
        number = float(value)
    if number != number or number <= 0 or number == float("inf"):
        return None
    return number


def apply_meta_opt_preset(
    repo_root: str | Path,
    settings: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return ``(settings, evidence)``; evidence is None when the flag is off."""
    result = dict(settings)
    if not meta_opt_preset_enabled(env):
        return result, None

    source = env if env is not None else os.environ
    report_path = Path(source.get(REPORT_ENV_VAR) or DEFAULT_REPORT)
    if not report_path.is_absolute():
        report_path = Path(repo_root) / report_path
    evidence: dict[str, Any] = {
        "enabled": True,
        "applied": False,
        "reason": "",
        "report_path": str(report_path),
        "report_sha256": None,
        "applied_keys": {},
        "rejected_keys": {},
        "ignored_keys": [],
    }

    try:
        raw = report_path.read_bytes()
    except OSError as exc:
        evidence["reason"] = f"report_unreadable:{type(exc).__name__}"
        return result, evidence
    evidence["report_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        report = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        evidence["reason"] = "report_malformed"
        return result, evidence
    if not isinstance(report, dict):
        evidence["reason"] = "report_malformed"
        return result, evidence
    if report.get("status") != "ok":
        evidence["reason"] = f"report_status_{report.get('status')}"
        return result, evidence
    selected = report.get("selected_preset")
    if not isinstance(selected, dict) or not isinstance(selected.get("preset"), dict):
        evidence["reason"] = "no_selected_preset"
        return result, evidence
    if report.get("simulated") is True or selected.get("status") != "ok":
        evidence["reason"] = "simulated_or_unmeasured_preset"
        return result, evidence
    child = selected.get("report_file")
    if child:
        child_path = Path(str(child))
        if not child_path.is_absolute():
            child_path = Path(repo_root) / child_path
        try:
            child_payload = json.loads(child_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            child_payload = None
        if isinstance(child_payload, dict) and child_payload.get("simulated") is True:
            evidence["reason"] = "source_report_simulated"
            return result, evidence

    preset = selected["preset"]
    evidence["preset_name"] = str(selected.get("preset_name", preset.get("name", "")))
    for key, value in preset.items():
        mapping = PRESET_KEY_MAP.get(key)
        if mapping is None:
            evidence["ignored_keys"].append(key)
            continue
        target, kind = mapping
        coerced = _coerce(value, kind)
        if coerced is None:
            evidence["rejected_keys"][key] = f"invalid_value:{value!r}"
            continue
        evidence["applied_keys"][target] = {"from": result.get(target), "to": coerced}
        result[target] = coerced
    evidence["applied"] = bool(evidence["applied_keys"])
    evidence["reason"] = "applied" if evidence["applied"] else "no_mappable_keys"
    return result, evidence
