from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path

from nexus.core.contained_write import PathContainmentError, read_text_in_root
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
    # Read once, never through a link, a hard link or a FIFO when there is a root to contain to
    # (#3037 follow-up): a link would hash a file outside source_root, a FIFO blocks forever.
    source_text: str | None = None
    if source_root:
        relative = os.path.normpath(target_file)
        try:
            if os.path.lexists(os.path.join(source_root, relative)):
                source_text = read_text_in_root(source_root, relative)
        except PathContainmentError as exc:
            return LocalModelSourceAnchor(
                target_file=target_file,
                target_symbol=target_symbol,
                blockers=("source_anchor_missing",),
                telemetry={"source_anchor_read_refused": str(exc)},
            )
    elif source_file_path.exists():
        try:
            source_text = source_file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            source_text = None
    
    explicit_locked_search = bool(locked_search.strip())
    localizer_attempted = False
    localizer_success = False
    localizer_error = ""
    localizer_source = "none"
    
    # 若無 explicit locked_search，嘗試 GranularMethodLocalizer 作為最後 fallback
    if not explicit_locked_search and source_text is not None:
        localizer_attempted = True
        try:
            from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer
            localizer = GranularMethodLocalizer()
            content = source_text
            bundle = localizer.localize(target_file, content, target_symbol)
            if bundle.primary_snippet:
                locked_search = bundle.primary_snippet
                localizer_success = True
                localizer_source = bundle.fallback_mode or "granular_method"
        except Exception as e:
            localizer_error = str(e)
            
    res = get_canonical_search_span(
        locked_search=locked_search,
        patch_diff=patch_diff,
        source_file=source_file_path if source_text is not None else None,
        target_symbol=target_symbol,
        source_text=source_text,
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
    if start_line == 0 and end_line == 0 and res.span and source_text is not None:
        try:
            content = source_text
            lines = content.splitlines()
            span_text = res.span if isinstance(res.span, str) else str(res.span)
            span_lines = [sl.strip() for sl in span_text.strip().splitlines() if sl.strip()]
            if span_lines:
                for i in range(len(lines) - len(span_lines) + 1):
                    file_sub = [lines[i+j].strip() for j in range(len(span_lines))]
                    if file_sub == span_lines:
                        start_line = i + 1
                        end_line = i + len(span_lines)
                        break
        except Exception:
            pass
            
    fallback = (res.source in ("ast_boundary", "traceback_window"))
    span_text = res.span if isinstance(res.span, str) else str(res.span)
    span_hash = hashlib.sha256(span_text.strip().encode("utf-8")).hexdigest()
    
    # If locked_search was filled by localizer (not explicit), override source to avoid
    # pretending the localizer snippet is an explicit locked_search.
    if not explicit_locked_search and localizer_success:
        effective_source = localizer_source or "granular_localizer"
    else:
        effective_source = res.source
    
    telemetry = dict(res.telemetry)
    telemetry.update({
        "target_symbol": target_symbol,
        "ast_symbol_found": (res.source == "ast_boundary"),
        "canonical_span_source": effective_source,
        "fallback_used": fallback,
        "span_hash": span_hash,
        "explicit_locked_search": explicit_locked_search,
        "localizer_fallback_attempted": localizer_attempted,
        "localizer_fallback_success": localizer_success,
        "localizer_fallback_error": localizer_error,
        "localizer_fallback_source": localizer_source,
    })
    
    return LocalModelSourceAnchor(
        target_file=target_file,
        target_symbol=target_symbol,
        canonical_span_source=effective_source,
        span_start=start_line,
        span_end=end_line,
        span_hash=span_hash,
        fallback_used=fallback,
        blockers=(),
        telemetry=telemetry,
    )
