"""Bounded AST-backed code-integrity evidence for one Candidate.

This module is a verifier evidence producer only. It does not select scope,
authorize mutation, decide Completion, or scan the repository outside the
Candidate paths supplied by CandidateVerifier.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


@dataclass(frozen=True)
class CodeIntegrityFinding:
    code: str
    path: str
    line: int
    detail: str


@dataclass(frozen=True)
class CodeIntegrityResult:
    schema: str
    passed: bool
    scanned_paths: tuple[str, ...]
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    target_references: tuple[str, ...]
    findings: tuple[CodeIntegrityFinding, ...]
    verifier_source_sha256: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "passed": self.passed,
            "scanned_paths": list(self.scanned_paths),
            "production_paths": list(self.production_paths),
            "test_paths": list(self.test_paths),
            "target_references": list(self.target_references),
            "findings": [asdict(item) for item in self.findings],
            "verifier_source_sha256": self.verifier_source_sha256,
            "evidence_sha256": self.evidence_sha256,
        }


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _is_test_path(path: str) -> bool:
    pure = path.replace("\\", "/")
    name = PurePosixPath(pure).name
    return (
        pure.startswith("tests/")
        or "/tests/" in f"/{pure}"
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _protocol_method_ids(tree: ast.AST) -> set[int]:
    methods: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if "Protocol" not in {_base_name(base) for base in node.bases}:
            continue
        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.add(id(statement))
    return methods


def _resolve_repository_module(
    repository_root: Path,
    module_name: str,
) -> str | None:
    if not module_name or module_name.startswith("."):
        return None
    module_parts = tuple(part for part in module_name.split(".") if part)
    if not module_parts:
        return None
    candidates = (
        repository_root.joinpath(*module_parts).with_suffix(".py"),
        repository_root.joinpath(*module_parts, "__init__.py"),
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(repository_root).as_posix()
        except (OSError, ValueError):
            continue
        if resolved.is_file() and not _is_test_path(relative):
            return relative
    return None


def _test_repository_references(
    repository_root: Path,
    source: str,
) -> tuple[str, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    references: set[str] = set()
    for node in ast.walk(tree):
        module_names: list[str] = []
        if isinstance(node, ast.Import):
            module_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module_names.append(node.module)
            module_names.extend(
                f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*"
            )
        for module_name in module_names:
            reference = _resolve_repository_module(repository_root, module_name)
            if reference is not None:
                references.add(reference)
    return tuple(sorted(references))


def _effective_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        current = decorator
        if isinstance(current, ast.Call):
            current = current.func
        if isinstance(current, ast.Name):
            names.add(current.id)
        elif isinstance(current, ast.Attribute):
            names.add(current.attr)
    return names


def _is_obvious_stub(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if _decorator_names(node) & {"abstractmethod", "overload"}:
        return False
    body = _effective_body(node)
    if not body:
        return True
    return all(
        isinstance(statement, ast.Pass)
        or (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value is Ellipsis
        )
        for statement in body
    )


def _scan_python(path: str, source: str, *, test_path: bool) -> list[CodeIntegrityFinding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [
            CodeIntegrityFinding(
                code="PYTHON_SYNTAX_INVALID",
                path=path,
                line=int(exc.lineno or 0),
                detail=str(exc.msg or "invalid Python syntax"),
            )
        ]

    findings: list[CodeIntegrityFinding] = []
    if test_path:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assert)
                and isinstance(node.test, ast.Constant)
                and node.test.value is True
            ):
                findings.append(
                    CodeIntegrityFinding(
                        code="TAUTOLOGICAL_TEST_ASSERT_TRUE",
                        path=path,
                        line=int(getattr(node, "lineno", 0) or 0),
                        detail="standalone executable assert True does not exercise target behavior",
                    )
                )
        return findings

    protocol_methods = _protocol_method_ids(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and id(node) not in protocol_methods
            and _is_obvious_stub(node)
        ):
            findings.append(
                CodeIntegrityFinding(
                    code="OBVIOUS_IMPLEMENTATION_STUB",
                    path=path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    detail=f"{node.name} has no executable implementation beyond pass/ellipsis",
                )
            )
    return findings


def run_code_integrity_v1(
    root: str | Path,
    *,
    changed_files: Iterable[str],
    untracked_files: Iterable[str],
    deleted_files: Iterable[str] = (),
) -> CodeIntegrityResult:
    repository_root = Path(root).resolve()
    deleted = set(deleted_files)
    candidate_paths = tuple(
        sorted(
            path
            for path in set(changed_files) | set(untracked_files)
            if path not in deleted and path.endswith(".py")
        )
    )
    production_paths = tuple(path for path in candidate_paths if not _is_test_path(path))
    test_paths = tuple(path for path in candidate_paths if _is_test_path(path))

    findings: list[CodeIntegrityFinding] = []
    target_references: set[str] = set()
    for relative in candidate_paths:
        absolute = (repository_root / relative).resolve()
        try:
            absolute.relative_to(repository_root)
        except ValueError:
            findings.append(
                CodeIntegrityFinding(
                    code="CANDIDATE_PATH_ESCAPE",
                    path=relative,
                    line=0,
                    detail="candidate path resolves outside repository root",
                )
            )
            continue
        try:
            source = absolute.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                CodeIntegrityFinding(
                    code="PYTHON_SOURCE_UNREADABLE",
                    path=relative,
                    line=0,
                    detail=str(exc),
                )
            )
            continue
        test_path = _is_test_path(relative)
        findings.extend(_scan_python(relative, source, test_path=test_path))
        if test_path:
            target_references.update(_test_repository_references(repository_root, source))

    if test_paths and not production_paths and not target_references:
        findings.append(
            CodeIntegrityFinding(
                code="TEST_ONLY_REACHABILITY_UNPROVEN",
                path=test_paths[0],
                line=0,
                detail=(
                    "candidate changes only Python tests; this verifier has no changed production "
                    "target witness and therefore cannot upgrade test-only evidence into production-behavior proof"
                ),
            )
        )

    verifier_source_sha256 = _source_sha256()
    material = {
        "schema": "nexus.code_integrity_evidence.v1",
        "passed": not findings,
        "scanned_paths": list(candidate_paths),
        "production_paths": list(production_paths),
        "test_paths": list(test_paths),
        "target_references": sorted(target_references),
        "findings": [asdict(item) for item in findings],
        "verifier_source_sha256": verifier_source_sha256,
    }
    evidence_sha256 = hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()
    return CodeIntegrityResult(
        schema="nexus.code_integrity_evidence.v1",
        passed=not findings,
        scanned_paths=candidate_paths,
        production_paths=production_paths,
        test_paths=test_paths,
        target_references=tuple(sorted(target_references)),
        findings=tuple(findings),
        verifier_source_sha256=verifier_source_sha256,
        evidence_sha256=evidence_sha256,
    )


__all__ = [
    "CodeIntegrityFinding",
    "CodeIntegrityResult",
    "run_code_integrity_v1",
]
