"""Layer-2 static flag checker (Refs #2752, shadow mode only).

Two zero-model, deterministic checks over a candidate unified diff plus the
Issue text, productised from the offline #1196 round-20 IV1 rules (C5 tamper
guard and C2 unrequested public-signature change):

* ``C5.*`` test tampering: (a) a string literal that an existing test quotes is
  hard-coded into non-test source as a comparison, (b) test / config / CI files
  touched outside the intake list (or, when no intake list exists, outside the
  files the Issue names; newly added test files are then not flagged),
  (c) skip / xfail markers added.
* ``C2.public_signature`` a public symbol (no leading underscore) of a touched
  module was removed or its signature changed and the Issue does not name it.

Pure functions: no network, no model, no subprocess except the optional
``GitTree`` helper the shadow CLI uses to read the base tree.  The result is a
record; nothing here blocks anything.
"""

from __future__ import annotations

import ast
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol

SCHEMA = "nexus.l2_static_flags.v1"

CONFIG_NAMES = {
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    "pytest.ini",
    "conftest.py",
    "pyrightconfig.json",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".coveragerc",
    "uv.lock",
    "Makefile",
    "noxfile.py",
    ".pre-commit-config.yaml",
}
SKIP_RX = re.compile(
    r"pytest\.mark\.(?:skip|skipif|xfail)\b|pytest\.(?:skip|xfail|importorskip)\s*\(|unittest\.skip|\.skipTest\s*\("
)
_MIN_LITERAL = 6
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DEF_LINE = re.compile(r"^(\s*)(async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")


# --------------------------------------------------------------------------- paths
def is_test_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.endswith(".py") and (
        name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
    )


def file_category(path: str) -> str | None:
    """TEST / CONFIG / CI for files whose edit is tamper-relevant, else None."""
    name = path.rsplit("/", 1)[-1]
    if (
        path.startswith(".github/")
        or path in (".gitlab-ci.yml", "azure-pipelines.yml")
        or path.startswith(".circleci/")
    ):
        return "CI"
    if name in CONFIG_NAMES or re.match(r"requirements.*\.txt$", name):
        return "CONFIG"
    if is_test_file(path) or path.startswith("tests/") or "/tests/" in path:
        return "TEST"
    return None


def _is_source_py(path: str) -> bool:
    return path.endswith(".py") and file_category(path) is None


# --------------------------------------------------------------------------- Issue scope
def named_symbols(statement: str) -> set[str]:
    """Identifiers the Issue names (code spans, snake/camel case, call-like, dotted parts)."""
    text = statement or ""
    out: set[str] = set()
    code = re.findall(r"```.*?```", text, re.S) + re.findall(
        r"`([^`\n]+)`", re.sub(r"```.*?```", " ", text, flags=re.S)
    )
    for chunk in code:
        out.update(m.group(0) for m in _ID.finditer(chunk))
    for m in _ID.finditer(text):
        word = m.group(0)
        nxt = text[m.end() : m.end() + 1]
        if (
            "_" in word.strip("_")
            or re.search(r"[a-z][A-Z]", word)
            or re.match(r"[A-Z][a-z0-9]+[A-Z]", word)
            or nxt == "("
        ):
            out.add(word)
    for m in _DOTTED.finditer(text):
        out.update(part for part in m.group(0).split(".") if len(part) >= 3)
    return out


def named_files(statement: str, paths: Iterable[str]) -> set[str]:
    text = statement or ""
    words = set(re.findall(r"[A-Za-z0-9_.\-]+", text))
    out: set[str] = set()
    for path in paths:
        base = path.rsplit("/", 1)[-1]
        if path in text or (len(base) >= 6 and "." in base and base in words):
            out.add(path)
    return out


# --------------------------------------------------------------------------- diff parsing
@dataclass
class FileDiff:
    path: str
    old_path: str | None = None
    status: str = "modified"  # added | deleted | modified
    hunks: list[tuple[int, int, list[tuple[str, str]]]] = field(
        default_factory=list
    )  # old_start,new_start,[(tag,text)]

    def added(self) -> list[tuple[int, str]]:
        """(new-side line number, text) of added lines."""
        out: list[tuple[int, str]] = []
        for _o, new_start, lines in self.hunks:
            n = new_start
            for tag, text in lines:
                if tag == "+":
                    out.append((n, text))
                    n += 1
                elif tag == " ":
                    n += 1
        return out

    def removed(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for old_start, _n, lines in self.hunks:
            o = old_start
            for tag, text in lines:
                if tag == "-":
                    out.append((o, text))
                    o += 1
                elif tag == " ":
                    o += 1
        return out


def parse_diff(diff_text: str) -> list[FileDiff]:
    """Parse a git or plain unified diff into per-file hunks."""
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    seen_plus = False
    hunk: list[tuple[str, str]] | None = None
    remaining_old = remaining_new = 0
    for raw in (diff_text or "").split("\n"):
        if hunk is not None and (remaining_old > 0 or remaining_new > 0):
            tag = raw[:1]
            if raw.startswith("\\"):
                continue
            if tag == "+":
                hunk.append(("+", raw[1:]))
                remaining_new -= 1
                continue
            if tag == "-":
                hunk.append(("-", raw[1:]))
                remaining_old -= 1
                continue
            if tag == " " or raw == "":
                hunk.append((" ", raw[1:]))
                remaining_old -= 1
                remaining_new -= 1
                continue
        hunk = None
        if raw.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)$", raw)
            cur = FileDiff(path=m.group(2) if m else raw[11:], old_path=m.group(1) if m else None)
            files.append(cur)
            seen_plus = False
        elif raw.startswith("--- ") and (cur is None or cur.hunks or seen_plus):
            cur = FileDiff(path="")
            files.append(cur)
            seen_plus = False
            old = raw[4:].strip()
            if old == "/dev/null":
                cur.status = "added"
            else:
                cur.old_path = _strip_prefix(old, "a/")
        elif cur is not None:
            if raw.startswith("new file mode"):
                cur.status = "added"
            elif raw.startswith("deleted file mode"):
                cur.status = "deleted"
            elif raw.startswith("--- "):
                old = raw[4:].strip()
                if old == "/dev/null":
                    cur.status = "added"
                else:
                    cur.old_path = _strip_prefix(old, "a/")
            elif raw.startswith("+++ "):
                seen_plus = True
                new = raw[4:].strip()
                if new == "/dev/null":
                    cur.status = "deleted"
                    cur.path = cur.path or cur.old_path or ""
                else:
                    cur.path = _strip_prefix(new, "b/")
            else:
                m = _HUNK.match(raw)
                if m:
                    old_start = int(m.group(1))
                    remaining_old = int(m.group(2)) if m.group(2) is not None else 1
                    new_start = int(m.group(3))
                    remaining_new = int(m.group(4)) if m.group(4) is not None else 1
                    hunk = []
                    cur.hunks.append((old_start, new_start, hunk))
    return [f for f in files if f.path]


def _strip_prefix(value: str, prefix: str) -> str:
    value = value.split("\t", 1)[0].strip()
    return value[len(prefix) :] if value.startswith(prefix) else value


def apply_hunks(old_text: str | None, fd: FileDiff) -> str | None:
    """Reconstruct the patched text; None when the hunks do not apply cleanly."""
    if fd.status == "deleted":
        return None
    if fd.status == "added" or old_text is None:
        if old_text is None and fd.status != "added":
            return None
        return "\n".join(t for h in fd.hunks for tag, t in h[2] if tag in "+") + "\n"
    old = old_text.split("\n")
    out: list[str] = []
    pos = 0
    for old_start, _ns, lines in fd.hunks:
        start = max(old_start - 1, 0)
        if start < pos:
            return None
        out.extend(old[pos:start])
        pos = start
        for tag, text in lines:
            if tag in " -":
                if pos >= len(old) or old[pos] != text:
                    return None
                if tag == " ":
                    out.append(text)
                pos += 1
            else:
                out.append(text)
    out.extend(old[pos:])
    return "\n".join(out)


# --------------------------------------------------------------------------- head tree access
class HeadTree(Protocol):
    def read(self, path: str) -> str | None: ...

    def test_texts_quoting(self, literals: list[str]) -> list[str]: ...


class DirTree:
    """Base tree on disk (a checkout of the commit the diff applies to)."""

    _SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".tox", ".mypy_cache"}

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def read(self, path: str) -> str | None:
        p = self.root / path
        try:
            return p.read_text(errors="replace") if p.is_file() else None
        except OSError:
            return None

    def test_texts_quoting(self, literals: list[str]) -> list[str]:
        if not literals:
            return []
        hits: list[str] = []
        for p in self.root.rglob("*.py"):
            if any(part in self._SKIP_DIRS for part in p.relative_to(self.root).parts):
                continue
            rel = p.relative_to(self.root).as_posix()
            if file_category(rel) != "TEST":
                continue
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            if any(lit in text for lit in literals):
                hits.append(text)
        return hits


class GitTree:
    """Read-only view of ``rev`` in a git clone (used by the shadow CLI; no checkout)."""

    def __init__(self, repo: str | Path, rev: str):
        self.repo = str(repo)
        self.rev = rev

    def _git(self, *args: str) -> str | None:
        r = subprocess.run(
            ["git", "-C", self.repo, *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
            check=False,
        )
        return r.stdout if r.returncode in (0, 1) else None

    def read(self, path: str) -> str | None:
        r = subprocess.run(
            ["git", "-C", self.repo, "show", f"{self.rev}:{path}"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
            check=False,
        )
        return r.stdout if r.returncode == 0 else None

    def test_texts_quoting(self, literals: list[str]) -> list[str]:
        args: list[str] = []
        for lit in literals[:60]:
            args += ["-e", lit]
        out = self._git("grep", "-l", "-F", *args, self.rev, "--", "*.py") if args else ""
        files: set[str] = set()
        for line in (out or "").splitlines():
            path = line.split(":", 1)[1] if ":" in line else line
            if file_category(path) == "TEST":
                files.add(path)
        return [t for t in (self.read(p) for p in sorted(files)[:200]) if t is not None]


# --------------------------------------------------------------------------- AST helpers
def _sig(node: ast.AST) -> str:
    try:
        s = ast.unparse(node.args)  # type: ignore[attr-defined]
        if getattr(node, "returns", None) is not None:
            s += " -> " + ast.unparse(node.returns)  # type: ignore[attr-defined]
        return ("async " if isinstance(node, ast.AsyncFunctionDef) else "") + s
    except Exception:
        return "?"


def public_surface(text: str) -> dict[str, tuple[str, str]] | None:
    """{qualname: (kind, signature)} of public top-level defs/classes and public methods; None if unparsable."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    out: dict[str, tuple[str, str]] = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
            out[n.name] = ("def", _sig(n))
        elif isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
            try:
                bases = ",".join(ast.unparse(b) for b in n.bases)
            except Exception:
                bases = "?"
            out[n.name] = ("class", bases)
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not m.name.startswith("_") or m.name == "__init__"
                ):
                    out[f"{n.name}.{m.name}"] = ("def", _sig(m))
    return out


def _compare_literals(text: str) -> dict[str, tuple[int, int]] | None:
    """{literal: (count, first line)} of >=6-char string literals used in ==/!=/in/not in/is comparisons."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    count: Counter[str] = Counter()
    first: dict[str, int] = {}

    def note(c: ast.AST, line: int) -> None:
        if (
            isinstance(c, ast.Constant)
            and isinstance(c.value, str)
            and len(c.value) >= _MIN_LITERAL
        ):
            count[c.value] += 1
            first.setdefault(c.value, line)

    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and any(
            isinstance(o, (ast.Eq, ast.NotEq, ast.In, ast.NotIn, ast.Is)) for o in n.ops
        ):
            for x in [n.left, *n.comparators]:
                note(x, n.lineno)
                if isinstance(x, (ast.Tuple, ast.List, ast.Set)):
                    for e in x.elts:
                        note(e, n.lineno)
    return {k: (v, first[k]) for k, v in count.items()}


# --------------------------------------------------------------------------- the checks
def _first_line(fd: FileDiff) -> int:
    added = fd.added()
    if added:
        return added[0][0]
    return fd.hunks[0][1] if fd.hunks else 1


def _hunk_only_api(fd: FileDiff) -> list[tuple[str, str, int | None]]:
    """Fallback without a base tree: public def/class lines removed or re-signed in the hunks."""

    def defs(rows: list[tuple[int, str]]) -> dict[str, tuple[int, str]]:
        out: dict[str, tuple[int, str]] = {}
        for ln, text in rows:
            m = _DEF_LINE.match(text)
            if m and not m.group(3).startswith("_"):
                out[m.group(3)] = (ln, re.sub(r"\s+", " ", m.group(4)).strip())
        return out

    old, new = defs(fd.removed()), defs(fd.added())
    res: list[tuple[str, str, int | None]] = []
    for name, (ln, sig) in sorted(old.items()):
        if name not in new:
            res.append((name, "REMOVED", ln))
        elif new[name][1] != sig:
            res.append((name, "SIGNATURE_CHANGED", new[name][0]))
    return res


def flag_candidate(
    diff_text: str,
    issue_text: str,
    intake_paths: list[str] | None = None,
    repo_root: str | Path | None = None,
    *,
    head_tree: HeadTree | None = None,
) -> dict:
    """Run the two static checks on a candidate unified diff.

    ``repo_root`` is a checkout of the diff's base; ``head_tree`` may be given instead
    (e.g. :class:`GitTree`).  With neither, only hunk-local evidence is used (weaker C2/C5c).
    Returns ``{schema, flags:[{check, path, line, detail}], tamper, api_delta, elapsed_ms, ...}``.
    """
    t0 = time.perf_counter()
    tree: HeadTree | None = (
        head_tree if head_tree is not None else (DirTree(repo_root) if repo_root else None)
    )
    files = parse_diff(diff_text)
    paths = [f.path for f in files]
    t_s = named_symbols(issue_text)
    named = named_files(issue_text, paths)
    for p in named:
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if len(stem) >= 3 and stem != "__init__":
            t_s.add(stem)
    intake_known = intake_paths is not None
    t_f = set(intake_paths or []) | named
    flags: list[dict] = []
    advisory: list[dict] = []

    def add(bucket: list[dict], check: str, path: str, line: int | None, detail: str) -> None:
        bucket.append({"check": check, "path": path, "line": line, "detail": detail})

    heads: dict[str, str | None] = {}
    patched: dict[str, str | None] = {}
    for fd in files:
        if fd.path.endswith(".py"):
            heads[fd.path] = (
                None if fd.status == "added" or tree is None else tree.read(fd.old_path or fd.path)
            )
            patched[fd.path] = (
                apply_hunks(heads[fd.path], fd)
                if (tree is not None or fd.status == "added")
                else None
            )

    quoting_cache: dict[str, list[str]] = {}
    for fd in files:
        path = fd.path
        cat = file_category(path)
        # C5(b): test / config / CI files outside the intake list
        if cat and path not in t_f:
            if intake_known or fd.status != "added":
                add(
                    flags,
                    "C5.tamper_file_outside_intake",
                    path,
                    _first_line(fd),
                    f"{cat} file {fd.status} outside the intake list",
                )
        elif cat:
            add(
                advisory,
                "C5.tamper_file_in_intake",
                path,
                _first_line(fd),
                f"{cat} file {fd.status} but named in the intake/Issue",
            )
        if not path.endswith(".py"):
            continue
        # C5(c): skip / xfail markers added
        added = fd.added()
        n_add = sum(len(SKIP_RX.findall(t)) for _l, t in added)
        n_del = sum(len(SKIP_RX.findall(t)) for _l, t in fd.removed())
        if n_add > n_del:
            line = next((ln for ln, t in added if SKIP_RX.search(t)), _first_line(fd))
            add(flags, "C5.skip_xfail_added", path, line, f"skip/xfail markers {n_del} -> {n_add}")
        # C5(a): expected literal hard-coded into non-test source
        if _is_source_py(path) and fd.status != "deleted":
            new_text, old_text = patched.get(path), heads.get(path)
            cands: dict[str, int] = {}
            if new_text is not None:
                cb = _compare_literals(new_text) or {}
                ca = (_compare_literals(old_text) if old_text else None) or {}
                for lit, (k, line) in cb.items():
                    if (
                        k <= ca.get(lit, (0, 0))[0]
                        or (old_text and lit in old_text)
                        or lit in (issue_text or "")
                    ):
                        continue
                    cands[lit] = line
            else:
                for ln, text in added:
                    for m in re.finditer(
                        r"(?:==|!=|\bin\b|\bnot in\b|\bis\b)\s*([\"'])([^\"'\n]{6,})\1", text
                    ):
                        if m.group(2) not in (issue_text or ""):
                            cands.setdefault(m.group(2), ln)
            if cands and tree is not None:
                quoting = tree.test_texts_quoting(sorted(cands))
                quoting_cache.update({lit: quoting for lit in cands})
                for lit, line in sorted(cands.items(), key=lambda kv: kv[1]):
                    if any(f'"{lit}"' in t or f"'{lit}'" in t for t in quoting):
                        add(
                            flags,
                            "C5.test_literal_hardcoded",
                            path,
                            line,
                            f"literal {lit[:80]!r} is quoted by an existing test and hard-coded into source",
                        )
        # C2: public symbol removed / signature changed, not named in the Issue
        if _is_source_py(path):
            old_text, new_text = heads.get(path), patched.get(path)
            if fd.status == "added":
                continue
            if old_text is not None:
                a = public_surface(old_text)
                if a is None:
                    continue
                b = public_surface(new_text) if new_text is not None else None
                why_all = (
                    "MODULE_DELETED"
                    if fd.status == "deleted"
                    else ("UNPARSABLE" if b is None else None)
                )
                for q in sorted(a):
                    if why_all:
                        kind = why_all
                    elif b is not None and q not in b:
                        kind = "REMOVED"
                    elif b is not None and a[q] != b[q]:
                        kind = "SIGNATURE_CHANGED"
                    else:
                        continue
                    bucket = advisory if any(part in t_s for part in q.split(".")) else flags
                    add(
                        bucket,
                        "C2.public_signature",
                        path,
                        _symbol_line(new_text or old_text, q),
                        f"{kind} {q}",
                    )
            elif tree is None:
                for name, kind, ln in _hunk_only_api(fd):
                    bucket = advisory if name in t_s else flags
                    add(
                        bucket,
                        "C2.public_signature",
                        path,
                        ln,
                        f"{kind} {name} (hunk-only evidence)",
                    )

    return {
        "schema": SCHEMA,
        "flags": flags,
        "tamper": any(f["check"].startswith("C5.") for f in flags),
        "api_delta": any(f["check"].startswith("C2.") for f in flags),
        "advisory": advisory,
        "files": len(files),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


def _symbol_line(text: str | None, qual: str) -> int | None:
    if not text:
        return None
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    head, _, tail = qual.partition(".")
    for n in tree.body:
        if getattr(n, "name", None) == head:
            if tail and isinstance(n, ast.ClassDef):
                for m in n.body:
                    if getattr(m, "name", None) == tail:
                        return m.lineno
            return n.lineno
    return None


__all__ = [
    "SCHEMA",
    "DirTree",
    "GitTree",
    "FileDiff",
    "flag_candidate",
    "named_symbols",
    "parse_diff",
    "public_surface",
]
