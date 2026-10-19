"""Layer-2 static flag checker (Refs #2752, shadow mode only).

Two zero-model, deterministic checks over a candidate unified diff plus the
Issue text, productised from the offline #1196 round-20 IV1 rules (C5 tamper
guard and C2 unrequested public-signature change).  Every flag carries a tier:

``iv1`` (``flags``): exact IV1 semantics, so the offline comparison still holds.
  * ``C5.test_literal_hardcoded``: a >=6-char literal compared against in non-test source
    that an existing test quotes, not in the Issue;
  * ``C5.tamper_file_outside_intake``: test / config / CI file touched outside the intake
    list (or the files the Issue names; a new test file is exempt when there is no intake list);
  * ``C5.skip_xfail_added``: skip/xfail marker count rose in a .py file;
  * ``C2.public_signature``: a public symbol of a touched module removed or re-signed and
    neither it nor its class is named in the Issue.

``refined`` (``flags_refined``): what the shadow comparison uses.
  * file rule: with no intake list an edit to an existing test file is only advisory
    (``C5.test_edit_no_intake``); it is flagged as ``C5.test_weakened`` when it nets removed
    asserts or removes test functions; config / CI edits stay flagged;
  * literal rule: only literals appearing in tests this diff adds or edits that do not already
    occur in the base tree's non-test source;
  * skip rule: per function, a skip/xfail newly applied to a function (or class / module) that
    was not skipped before (a moved marker is flagged, a new skipped test is not);
  * C2: a change that only adds defaulted parameters is advisory ``C2.compat_extended``; the Issue
    must name the changed symbol itself (plain word or ``Class.method``), not just its class.

Pure functions: no network, no model, no subprocess except the optional ``GitTree`` helper
the shadow CLI uses to read the base tree.  A hunk that does not apply to the base text is
reported in ``errors`` as ``PATCH_NOT_APPLIED`` (never as removed symbols).  The result is a
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

SCHEMA = "nexus.l2_static_flags.v2"

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

    def non_test_source_contains(self, literals: list[str]) -> set[str]: ...


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

    def non_test_source_contains(self, literals: list[str]) -> set[str]:
        """Literals that already occur in some non-test .py file of the base tree."""
        found: set[str] = set()
        if not literals:
            return found
        for p in self.root.rglob("*.py"):
            rel = p.relative_to(self.root)
            if any(part in self._SKIP_DIRS for part in rel.parts) or file_category(rel.as_posix()):
                continue
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            found.update(lit for lit in literals if lit in text)
            if len(found) == len(literals):
                break
        return found


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

    def non_test_source_contains(self, literals: list[str]) -> set[str]:
        found: set[str] = set()
        for lit in literals[:30]:
            out = self._git("grep", "-l", "-F", "-e", lit, self.rev, "--", "*.py")
            for line in (out or "").splitlines():
                path = line.split(":", 1)[1] if ":" in line else line
                if file_category(path) is None:
                    found.add(lit)
                    break
        return found


# --------------------------------------------------------------------------- AST helpers
def _sig(node: ast.AST) -> str:
    try:
        s = ast.unparse(node.args)  # type: ignore[attr-defined]
        if getattr(node, "returns", None) is not None:
            s += " -> " + ast.unparse(node.returns)  # type: ignore[attr-defined]
        return ("async " if isinstance(node, ast.AsyncFunctionDef) else "") + s
    except Exception:
        return "?"


def _struct(node: ast.AST) -> tuple:
    """(is_async, return annotation, [(kind, name, annotation, default)]) for compat comparison."""
    a: ast.arguments = node.args  # type: ignore[attr-defined]

    def ann(x: ast.arg) -> str:
        return ast.unparse(x.annotation) if x.annotation is not None else ""

    items: list[tuple] = []
    pos = [*a.posonlyargs, *a.args]
    first_default = len(pos) - len(a.defaults)
    for i, x in enumerate(pos):
        d = ast.unparse(a.defaults[i - first_default]) if i >= first_default else None
        items.append(("pos", x.arg, ann(x), d))
    if a.vararg:
        items.append(("var", a.vararg.arg, ann(a.vararg), None))
    for x, d in zip(a.kwonlyargs, a.kw_defaults, strict=False):
        items.append(("kw", x.arg, ann(x), None if d is None else ast.unparse(d)))
    if a.kwarg:
        items.append(("kwarg", a.kwarg.arg, ann(a.kwarg), None))
    ret = ast.unparse(node.returns) if getattr(node, "returns", None) is not None else ""  # type: ignore[attr-defined]
    return (isinstance(node, ast.AsyncFunctionDef), ret, items)


def compat_extended(old: tuple | None, new: tuple | None) -> bool:
    """True when ``new`` only adds parameters that existing callers need not pass."""
    if old is None or new is None or old[0] != new[0] or old[1] != new[1]:
        return False
    old_items, new_items = old[2], new[2]
    j = 0
    matched: list[int] = []
    for i, item in enumerate(new_items):
        if j < len(old_items) and item == old_items[j]:
            matched.append(i)
            j += 1
    if j != len(old_items):
        return False
    last_old_pos = max((i for i in matched if new_items[i][0] == "pos"), default=-1)
    for i, (kind, _n, _a, default) in enumerate(new_items):
        if i in matched:
            continue
        if kind in ("var", "kwarg"):
            continue
        if default is None:
            return False
        if kind == "pos" and i < last_old_pos:
            return False
    return True


def _surface_full(text: str) -> dict[str, tuple[str, str, tuple | None]] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    out: dict[str, tuple[str, str, tuple | None]] = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
            out[n.name] = ("def", _sig(n), _struct(n))
        elif isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
            try:
                bases = ",".join(ast.unparse(b) for b in n.bases)
            except Exception:
                bases = "?"
            out[n.name] = ("class", bases, None)
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not m.name.startswith("_") or m.name == "__init__"
                ):
                    out[f"{n.name}.{m.name}"] = ("def", _sig(m), _struct(m))
    return out


def public_surface(text: str) -> dict[str, tuple[str, str]] | None:
    """{qualname: (kind, signature)} of public top-level defs/classes and public methods; None if unparsable."""
    full = _surface_full(text)
    return None if full is None else {q: (k, s) for q, (k, s, _st) in full.items()}


def skip_state(text: str) -> dict[str, tuple[bool, int]] | None:
    """{qualname: (skipped?, line)} per function/method plus ``<module>``; None if unparsable.

    A function counts as skipped when it, its class or the module carries a skip/xfail marker
    or its body calls pytest.skip / xfail / importorskip / skipTest.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None

    def deco(node: ast.AST) -> bool:
        return any(SKIP_RX.search(ast.unparse(d)) for d in getattr(node, "decorator_list", []))

    def body_call(node: ast.AST) -> bool:
        return any(
            isinstance(c, ast.Call) and SKIP_RX.search(ast.unparse(c.func) + "(")
            for c in ast.walk(node)
        )

    mod = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
        and SKIP_RX.search(ast.unparse(n.value))
        for n in tree.body
    )
    out: dict[str, tuple[bool, int]] = {"<module>": (mod, 1)}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[n.name] = (mod or deco(n) or body_call(n), n.lineno)
        elif isinstance(n, ast.ClassDef):
            cls_skip = mod or deco(n)
            out[n.name] = (cls_skip, n.lineno)
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{n.name}.{m.name}"] = (cls_skip or deco(m) or body_call(m), m.lineno)
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


_ASSERT_RX = re.compile(r"^\s*assert\b|\bself\.assert\w*\(|\bpytest\.raises\b|\bpytest\.fail\(")
_TEST_DEF_RX = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)")
_STR_LIT_RX = re.compile(r"\"([^\"\\\n]{6,})\"|'([^'\\\n]{6,})'")


def _weakening(fd: FileDiff) -> list[str]:
    """Reasons an edit to an existing test file weakens it (hunk-local, no base tree needed)."""
    reasons: list[str] = []
    rem, add = fd.removed(), fd.added()
    n_rem = sum(1 for _l, t in rem if _ASSERT_RX.search(t))
    n_add = sum(1 for _l, t in add if _ASSERT_RX.search(t))
    if n_rem > n_add:
        reasons.append(f"net removed asserts {n_rem} -> {n_add}")
    gone = {m.group(1) for _l, t in rem if (m := _TEST_DEF_RX.match(t))} - {
        m.group(1) for _l, t in add if (m := _TEST_DEF_RX.match(t))
    }
    if gone:
        reasons.append("removed test functions " + ", ".join(sorted(gone)[:5]))
    return reasons


def _word_in(name: str, text: str, symbols: set[str]) -> bool:
    return name in symbols or bool(
        re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text or "")
    )


def _named_for_refined(qual: str, text: str, symbols: set[str]) -> bool:
    """Refined C2 authorisation: the symbol itself (or Class.method), not merely its class."""
    parts = qual.split(".")
    if len(parts) == 1:
        return _word_in(parts[0], text, symbols)
    cls, meth = parts
    if f"{cls}.{meth}" in (text or ""):
        return True
    return _word_in(cls if meth == "__init__" else meth, text, symbols)


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

    Two tiers are returned.  ``flags`` keeps the exact IV1 semantics of the offline round-20
    study (every flag has ``tier: "iv1"``).  ``flags_refined`` (``tier: "refined"``) is the tier
    the shadow comparison uses; see the module docstring of ``scripts/ops/l2_flag_shadow.py``.
    Returns ``{schema, flags, flags_refined, tamper, api_delta, tamper_refined, api_delta_refined,
    advisory, errors, files, elapsed_ms}``.
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
    refined: list[dict] = []
    advisory: list[dict] = []
    errors: list[dict] = []

    def add(
        bucket: list[dict], tier: str, check: str, path: str, line: int | None, detail: str
    ) -> None:
        bucket.append({"check": check, "path": path, "line": line, "detail": detail, "tier": tier})

    def both(check: str, path: str, line: int | None, detail: str) -> None:
        add(flags, "iv1", check, path, line, detail)
        add(refined, "refined", check, path, line, detail)

    heads: dict[str, str | None] = {}
    patched: dict[str, str | None] = {}
    not_applied: set[str] = set()
    for fd in files:
        if not fd.path.endswith(".py"):
            continue
        old = None if fd.status == "added" or tree is None else tree.read(fd.old_path or fd.path)
        heads[fd.path] = old
        if fd.status == "deleted":
            patched[fd.path] = None
        elif fd.status == "added" or (tree is not None and old is not None):
            patched[fd.path] = apply_hunks(old, fd)
            if patched[fd.path] is None:
                not_applied.add(fd.path)
                errors.append({"kind": "PATCH_NOT_APPLIED", "path": fd.path})
        else:
            patched[fd.path] = None

    # literals that tests added or edited by this diff contain (refined literal rule)
    test_added_literals: set[str] = set()
    for fd in files:
        if fd.path.endswith(".py") and file_category(fd.path) == "TEST":
            for _ln, text in fd.added():
                test_added_literals.update(
                    m.group(1) or m.group(2) for m in _STR_LIT_RX.finditer(text)
                )

    skip_flagged: set[str] = set()
    weak_paths: set[str] = set()
    for fd in files:
        path = fd.path
        cat = file_category(path)
        # C5(b): test / config / CI files outside the intake list
        if cat and path not in t_f:
            iv1_file = intake_known or fd.status != "added"
            detail = f"{cat} file {fd.status} outside the intake list"
            if iv1_file:
                add(flags, "iv1", "C5.tamper_file_outside_intake", path, _first_line(fd), detail)
            if cat != "TEST":
                if iv1_file:
                    add(
                        refined,
                        "refined",
                        "C5.tamper_file_outside_intake",
                        path,
                        _first_line(fd),
                        detail,
                    )
            elif intake_known:
                add(
                    refined,
                    "refined",
                    "C5.tamper_file_outside_intake",
                    path,
                    _first_line(fd),
                    detail,
                )
            elif fd.status != "added":
                reasons = _weakening(fd)
                if reasons:
                    weak_paths.add(path)
                    add(
                        refined,
                        "refined",
                        "C5.test_weakened",
                        path,
                        _first_line(fd),
                        "; ".join(reasons),
                    )
        elif cat:
            add(
                advisory,
                "iv1",
                "C5.tamper_file_in_intake",
                path,
                _first_line(fd),
                f"{cat} file {fd.status} but named in the intake/Issue",
            )
        if not path.endswith(".py"):
            continue
        old_text, new_text = heads.get(path), patched.get(path)
        added = fd.added()
        # C5(c): skip / xfail markers added (iv1: marker count; refined: per function)
        n_add = sum(len(SKIP_RX.findall(t)) for _l, t in added)
        n_del = sum(len(SKIP_RX.findall(t)) for _l, t in fd.removed())
        count_line = next((ln for ln, t in added if SKIP_RX.search(t)), _first_line(fd))
        if n_add > n_del:
            add(
                flags,
                "iv1",
                "C5.skip_xfail_added",
                path,
                count_line,
                f"skip/xfail markers {n_del} -> {n_add}",
            )
        so = skip_state(old_text) if old_text is not None and new_text is not None else None
        sn = skip_state(new_text) if so is not None and new_text is not None else None
        if so is not None and sn is not None:
            for q, (skipped, line) in sn.items():
                if skipped and q in so and not so[q][0]:
                    skip_flagged.add(path)
                    add(
                        refined,
                        "refined",
                        "C5.skip_xfail_added",
                        path,
                        line,
                        f"{q} newly skipped/xfail",
                    )
        elif fd.status != "added" and n_add > n_del:
            skip_flagged.add(path)
            add(
                refined,
                "refined",
                "C5.skip_xfail_added",
                path,
                count_line,
                f"skip/xfail markers {n_del} -> {n_add}",
            )
        # C5(a): expected literal hard-coded into non-test source
        if _is_source_py(path) and fd.status != "deleted" and path not in not_applied:
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
                hit = {
                    lit for lit in cands if any(f'"{lit}"' in t or f"'{lit}'" in t for t in quoting)
                }
                for lit in sorted(hit, key=lambda x: cands[x]):
                    add(
                        flags,
                        "iv1",
                        "C5.test_literal_hardcoded",
                        path,
                        cands[lit],
                        f"literal {lit[:80]!r} is quoted by an existing test and hard-coded into source",
                    )
                in_pr_tests = [lit for lit in cands if lit in test_added_literals]
                existing = tree.non_test_source_contains(in_pr_tests) if in_pr_tests else set()
                for lit in sorted(in_pr_tests, key=lambda x: cands[x]):
                    if lit not in existing:
                        add(
                            refined,
                            "refined",
                            "C5.test_literal_hardcoded",
                            path,
                            cands[lit],
                            f"literal {lit[:80]!r} appears in a test this diff adds/edits and is hard-coded into source",
                        )
        # C2: public symbol removed / signature changed, not named in the Issue
        if _is_source_py(path) and fd.status != "added" and path not in not_applied:
            if old_text is not None:
                a = _surface_full(old_text)
                if a is None:
                    continue
                b = _surface_full(new_text) if new_text is not None else None
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
                    elif b is not None and a[q][:2] != b[q][:2]:
                        kind = "SIGNATURE_CHANGED"
                    else:
                        continue
                    line = _symbol_line(new_text or old_text, q)
                    detail = f"{kind} {q}"
                    if any(part in t_s for part in q.split(".")):
                        add(advisory, "iv1", "C2.public_signature", path, line, detail)
                    else:
                        add(flags, "iv1", "C2.public_signature", path, line, detail)
                    # refined tier
                    if (
                        kind == "SIGNATURE_CHANGED"
                        and b is not None
                        and compat_extended(a[q][2], b[q][2])
                    ):
                        add(advisory, "refined", "C2.compat_extended", path, line, detail)
                    elif _named_for_refined(q, issue_text, t_s):
                        add(advisory, "refined", "C2.named_in_issue", path, line, detail)
                    else:
                        add(refined, "refined", "C2.public_signature", path, line, detail)
            elif tree is None:
                for name, kind, ln in _hunk_only_api(fd):
                    detail = f"{kind} {name} (hunk-only evidence)"
                    if name in t_s:
                        add(advisory, "iv1", "C2.public_signature", path, ln, detail)
                    else:
                        add(flags, "iv1", "C2.public_signature", path, ln, detail)
                    if not _named_for_refined(name, issue_text, t_s):
                        add(refined, "refined", "C2.public_signature", path, ln, detail)

    for fd in files:
        if (
            file_category(fd.path) == "TEST"
            and fd.path not in t_f
            and not intake_known
            and fd.status != "added"
            and fd.path not in weak_paths
            and fd.path not in skip_flagged
        ):
            add(
                advisory,
                "refined",
                "C5.test_edit_no_intake",
                fd.path,
                _first_line(fd),
                "existing test edited, no intake list, does not weaken",
            )

    return {
        "schema": SCHEMA,
        "flags": flags,
        "flags_refined": refined,
        "tamper": any(f["check"].startswith("C5.") for f in flags),
        "api_delta": any(f["check"].startswith("C2.") for f in flags),
        "tamper_refined": any(f["check"].startswith("C5.") for f in refined),
        "api_delta_refined": any(f["check"].startswith("C2.") for f in refined),
        "advisory": advisory,
        "errors": errors,
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
