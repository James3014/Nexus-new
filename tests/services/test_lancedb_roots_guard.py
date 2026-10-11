"""Guard: LanceDB root literals live only in ``nexus/services/lancedb_roots.py``.

Call sites must resolve roots through ``resolve_lancedb_root``. Sites that
deliberately keep a literal are listed in ``ALLOWLIST`` with the reason.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESOLVER = "nexus/services/lancedb_roots.py"

ROOT_LITERAL_PATTERNS = {
    "vector_db root": re.compile(r"\.nexus/vector_db|[\"']vector_db[\"']"),
    "memory index root": re.compile(r"memory_index\.lancedb"),
    "knowledge root": re.compile(r"[\"']knowledge[\"']\s*/\s*[\"']lancedb[\"']|knowledge/lancedb"),
    "repository root": re.compile(
        r"\.nexus[\"']\s*/\s*[\"']memory_repository[\"']|\.nexus/memory_repository"
    ),
    "tenant jsonl root": re.compile(
        r"[\"']tenants[\"'].*[\"']lancedb[\"']|\.nexus/tenants/.*lancedb"
    ),
    "memory db env": re.compile(r"NEXUS_MEMORY_DB_PATH"),
}

# path -> reason the literal is intentionally kept
ALLOWLIST = {
    "scripts/ops/nexus_benchmark_preflight.py": (
        "sets/restores NEXUS_MEMORY_DB_PATH in the process env to a temp dir for the preflight; it names the "
        "env var to export it, it does not resolve a root"
    ),
    "scripts/bench/capability_ab_runner.py": (
        "exports NEXUS_MEMORY_DB_PATH into the benchmark subprocess env; it names the env var to set it, "
        "it does not resolve a root"
    ),
}


def _scan() -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for top in ("nexus", "scripts"):
        for path in sorted((REPO_ROOT / top).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel == RESOLVER:
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if line.lstrip().startswith("#"):
                    continue
                for label, pattern in ROOT_LITERAL_PATTERNS.items():
                    if pattern.search(line):
                        hits.setdefault(rel, []).append(f"{rel}:{lineno}: {label}: {line.strip()}")
    return hits


def test_no_hardcoded_lancedb_root_literals_outside_resolver():
    offenders = [
        entry for rel, entries in _scan().items() if rel not in ALLOWLIST for entry in entries
    ]
    assert not offenders, (
        "Use nexus.services.lancedb_roots.resolve_lancedb_root instead of hardcoding LanceDB roots "
        "(or add a reasoned ALLOWLIST entry):\n" + "\n".join(offenders)
    )


def test_lancedb_roots_allowlist_entries_are_live_and_reasoned():
    hits = _scan()
    for rel, reason in ALLOWLIST.items():
        assert reason.strip(), f"{rel} needs a reason"
        assert rel in hits, f"stale allowlist entry (no literal left in file): {rel}"
