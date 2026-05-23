from __future__ import annotations

from pathlib import Path


def is_strictly_doc_fix(task: str, target_file: str) -> tuple[bool, str]:
    path = Path(str(target_file or ""))
    suffix = path.suffix.lower()
    text = (task or "").lower()
    doc_suffix = suffix in {".md", ".rst", ".txt", ".adoc"}
    doc_words = any(word in text for word in ("docs", "documentation", "readme", "typo", "copy", "comment"))
    code_words = any(word in text for word in ("test", "runtime", "bug", "fix", "api", "logic", "function", "class"))
    if doc_suffix and doc_words and not code_words:
        return True, "doc_suffix_and_doc_language"
    return False, "not_strict_doc_fix"
