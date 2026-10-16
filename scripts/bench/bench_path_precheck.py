"""Counted-run start-up precheck: the bench paths must pass the prompt audit's string checks.

The resolved run root (an absolute path inside the bench worktree) is rendered into the
with-Nexus ``[NEXUS MODEL CONTEXT]`` block.  The prompt symmetry audit
(``prompt_symmetry_audit.classify_extra_lines`` / ``_schema_findings``) rejects a Nexus-block
string that is not an ``abs_path`` (``^/[A-Za-z0-9_./-]+$``), is longer than
``MAX_JSON_STRING_CHARS`` or carries a hidden-only word, line or literal of the task, in the
string itself or in any decoded variant (percent/base64/hex, ``_decoded_variants``).  Any of
these voids the whole counted run after the paid calls (``nexus_block_string_not_allowed``).
This precheck applies the same checks to the bench paths before any model call.  It reuses the
audit's own functions and never changes the audit.  Messages never print hidden text beyond
the single offending word (literals and lines are reported by length and sha256 prefix).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from scripts.bench import prompt_symmetry_audit as psa


def _fingerprint(text: str) -> str:
    return f"{len(text)} chars, sha256 {hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def bench_path_format_errors(paths: Iterable[str | Path]) -> list[str]:
    """Paths the audit would reject as a Nexus-block string regardless of the task."""

    errors: list[str] = []
    placeholder = psa.TaskMaterial(task_id="", visible_test="", hidden_test="")
    for path in dict.fromkeys(str(p) for p in paths if str(p)):
        if not psa._format_ok("abs_path", path, placeholder):
            errors.append(
                f"{path} is not a plain absolute path (audit abs_path: ^/[A-Za-z0-9_./-]+$)"
            )
        if len(path) > psa.MAX_JSON_STRING_CHARS:
            errors.append(
                f"{path} is longer than {psa.MAX_JSON_STRING_CHARS} chars (audit string limit)"
            )
    return errors


def bench_path_hidden_hits(
    paths: Iterable[str | Path],
    materials: Iterable[psa.TaskMaterial],
    *,
    rendered: Iterable[str | Path] | None = None,
) -> list[str]:
    """Every reason the audit would reject a bench path (empty = clean).

    ``paths`` get the hidden-text checks; ``rendered`` (the paths the runtime renders verbatim
    into the prompt; default: all of ``paths``) also get the audit's ``abs_path`` format and
    length checks.
    """

    texts = list(dict.fromkeys(str(path) for path in paths if str(path)))
    rendered_texts = texts if rendered is None else [str(p) for p in rendered if str(p)]
    texts = list(dict.fromkeys([*texts, *rendered_texts]))
    hits = bench_path_format_errors(rendered_texts)
    for material in materials:
        bare = psa.synthetic_bare_reference(material)
        bare_corpus = psa.normalize(bare)
        words = psa.hidden_only_words(material, bare)
        literals = [
            psa.normalize(literal)
            for literal in psa.hidden_only_literals(material)
            if psa.normalize(literal) not in bare_corpus
        ]
        lines = [line for line in psa.hidden_only_lines(material) if line not in bare_corpus]
        for text in texts:
            for variant in dict.fromkeys([text, *psa._decoded_variants(text)]):
                normalized = psa.normalize(variant)
                decoded = "" if variant == text else " (decoded)"
                for word in sorted(set(psa._WORD_RE.findall(normalized)) & words):
                    hits.append(
                        f"{material.task_id}: {text} contains hidden-only word {word!r}{decoded}"
                    )
                for literal in literals:
                    if literal and literal in normalized:
                        hits.append(
                            f"{material.task_id}: {text} contains a hidden-only literal "
                            f"({_fingerprint(literal)}){decoded}"
                        )
                for line in lines:
                    if line in normalized:
                        hits.append(
                            f"{material.task_id}: {text} contains a hidden test line "
                            f"({_fingerprint(line)}){decoded}"
                        )
    return list(dict.fromkeys(hits))
