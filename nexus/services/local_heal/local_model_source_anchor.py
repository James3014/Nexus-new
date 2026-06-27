from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path

from nexus.services.local_heal.canonical_span import get_canonical_search_span


@dataclass(frozen=True)
class LocalModelSourceAnchor:
    target_file: str
    target_symbol: str
    canonical_span_source: str = ""
    span_start: int = 0
    span_end: int = 0
    span_hash: str = ""
    fallback_used: bool = False
    blockers: tuple[str, ...] = ()
    telemetry: dict = field(default_factory=dict)


def build_local_model_source_anchor(
    source_root: str,
    target_file: str,
    target_symbol: str,
    patch_diff: str = "",
    locked_search: str = "",
) -> LocalModelSourceAnchor:
    
    source_file_path = Path(source_root) / target_file
    
    res = get_canonical_search_span(
        locked_search=locked_search,
        patch_diff=patch_diff,
        source_file=source_file_path if source_file_path.exists() else None,
        target_symbol=target_symbol,
    )
    
    if res is None:
        return LocalModelSourceAnchor(
            target_file=target_file,
            target_symbol=target_symbol,
            blockers=("source_anchor_missing",),
        )
        
    start_line = res.start_line
    end_line = res.end_line
    
    # 若 res 無行號資訊 (例如來自 locked_search 文字匹配)，且原始碼檔案存在，動態還原行號範圍
    if start_line == 0 and end_line == 0 and res.span and source_file_path.exists():
        try:
            content = source_file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            span_lines = res.span.strip().splitlines()
            for i in range(len(lines) - len(span_lines) + 1):
                if lines[i:i+len(span_lines)] == span_lines:
                    start_line = i + 1
                    end_line = i + len(span_lines)
                    break
        except Exception:
            pass
            
    fallback = (res.source in ("ast_boundary", "traceback_window"))
    span_hash = hashlib.sha256(res.span.strip().encode("utf-8")).hexdigest()
    
    telemetry = dict(res.telemetry)
    telemetry.update({
        "target_symbol": target_symbol,
        "ast_symbol_found": (res.source == "ast_boundary"),
        "canonical_span_source": res.source,
        "fallback_used": fallback,
        "span_hash": span_hash,
    })
    
    return LocalModelSourceAnchor(
        target_file=target_file,
        target_symbol=target_symbol,
        canonical_span_source=res.source,
        span_start=start_line,
        span_end=end_line,
        span_hash=span_hash,
        fallback_used=fallback,
        blockers=(),
        telemetry=telemetry,
    )
