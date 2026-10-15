"""Counted-run start-up precheck: no hidden-only word in the bench paths.

nexus-runtime renders the resolved run root (an absolute path inside the bench worktree) into
the with-Nexus ``[NEXUS MODEL CONTEXT]`` block.  The prompt symmetry audit
(``prompt_symmetry_audit.classify_extra_lines``) rejects any Nexus-block string carrying a
hidden-only word, line or literal of the task, so a bench path such as
``.../20261016-proof-main/...`` (``main`` is hidden-only for hard_v1 ``oabh-remote``) voids
the whole counted run after paying for it.  This precheck applies the same matching to the bench
paths before any model call and refuses to start.  It reuses the audit's own extraction
(``hidden_only_words`` against the synthetic bare reference, ``hidden_only_literals``,
``hidden_only_lines``) and never changes the audit.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from scripts.bench import prompt_symmetry_audit as psa


def bench_path_hidden_hits(
    paths: Iterable[str | Path], materials: Iterable[psa.TaskMaterial]
) -> list[str]:
    """``"<task_id>: <path> contains hidden-only <kind> <value>"`` for every hit (empty = clean)."""

    texts = [str(path) for path in paths if str(path)]
    hits: list[str] = []
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
            normalized = psa.normalize(text)
            for word in sorted(set(psa._WORD_RE.findall(normalized)) & words):
                hits.append(f"{material.task_id}: {text} contains hidden-only word {word!r}")
            for literal in literals:
                if literal and literal in normalized:
                    hits.append(
                        f"{material.task_id}: {text} contains hidden-only literal {literal!r}"
                    )
            for line in lines:
                if line in normalized:
                    hits.append(f"{material.task_id}: {text} contains a hidden test line")
    return hits
