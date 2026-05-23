from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class CodeIntelResultLike(Protocol):
    def to_dict(self) -> dict[str, Any]:
        ...


AnalyzeImpact = Callable[..., CodeIntelResultLike]
ScanCodebase = Callable[..., CodeIntelResultLike]
ContextForSymbol = Callable[..., CodeIntelResultLike]


@dataclass(frozen=True)
class CodeActionResult:
    payload: dict[str, Any]
    report_path: Path


def _default_analyze_impact(*args: Any, **kwargs: Any) -> CodeIntelResultLike:
    from nexus.services.codeintel import analyze_impact

    return analyze_impact(*args, **kwargs)


def _default_scan_codebase(*args: Any, **kwargs: Any) -> CodeIntelResultLike:
    from nexus.services.codeintel import scan_codebase

    return scan_codebase(*args, **kwargs)


def _default_context_for_symbol(*args: Any, **kwargs: Any) -> CodeIntelResultLike:
    from nexus.services.codeintel import context_for_symbol

    return context_for_symbol(*args, **kwargs)


def _report_path(repo_root: Path, report_file: str | Path | None, default_name: str) -> Path:
    out_path = Path(report_file) if report_file else repo_root / ".nexus" / "reports" / "codeintel" / default_name
    return out_path if out_path.is_absolute() else repo_root / out_path


def _write_json_report(payload: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def run_code_impact(
    repo_root: str | Path,
    *,
    files_text: str,
    index_path: str | None,
    report_file: str | Path | None,
    analyze_impact: AnalyzeImpact | None = None,
) -> CodeActionResult:
    root = Path(repo_root)
    changed_files = [item.strip() for item in files_text.split(",") if item.strip()]
    payload = (analyze_impact or _default_analyze_impact)(root, changed_files, index_path=index_path).to_dict()
    out_path = _report_path(root, report_file, "impact.json")
    payload["report_path"] = str(out_path)
    evidence_paths = list(payload.get("evidence_paths", []) or [])
    if str(out_path) not in evidence_paths:
        evidence_paths.append(str(out_path))
    payload["evidence_paths"] = evidence_paths
    _write_json_report(payload, out_path)
    return CodeActionResult(payload=payload, report_path=out_path)


def render_code_impact(result: CodeActionResult) -> list[str]:
    return [
        f"Code impact: {len(result.payload['impacted_files'])} impacted files, risk={result.payload['risk_score']}",
        f"Report: {result.report_path}",
    ]


def run_code_scan(
    repo_root: str | Path,
    *,
    index_path: str | None,
    report_file: str | Path | None,
    scan_codebase: ScanCodebase | None = None,
) -> CodeActionResult:
    root = Path(repo_root)
    payload = (scan_codebase or _default_scan_codebase)(root, index_path=index_path).to_dict()
    out_path = _report_path(root, report_file, "scan.json")
    _write_json_report(payload, out_path)
    return CodeActionResult(payload=payload, report_path=out_path)


def render_code_scan(result: CodeActionResult) -> list[str]:
    return [
        f"Code scan: {result.payload['nodes_count']} nodes, {result.payload['edges_count']} edges",
        f"Index: {result.payload['index_path']}",
        f"Report: {result.report_path}",
    ]


def run_code_context(
    repo_root: str | Path,
    *,
    symbol: str,
    index_path: str | None,
    report_file: str | Path | None,
    context_for_symbol: ContextForSymbol | None = None,
) -> CodeActionResult:
    root = Path(repo_root)
    payload = (context_for_symbol or _default_context_for_symbol)(root, symbol, index_path=index_path).to_dict()
    out_path = _report_path(root, report_file, "context.json")
    _write_json_report(payload, out_path)
    return CodeActionResult(payload=payload, report_path=out_path)


def render_code_context(result: CodeActionResult, *, symbol: str) -> list[str]:
    status_text = "found" if result.payload["found"] else f"missing:{result.payload['reason']}"
    return [
        f"Code context: {symbol} {status_text}",
        f"Report: {result.report_path}",
    ]
