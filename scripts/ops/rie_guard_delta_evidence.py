#!/usr/bin/env python3
"""RIE guard semantic delta -> advisory PR/reviewer evidence (Issue #1580).

Collects normalized old/new guard evidence for ONE mechanically normalizable
guard family (the declarative ``CANONICAL_OWNERS`` table of
``scripts/ops/canonical_owner_guard.py``) from an exact base/head pair, asks the
canonical Repository Intelligence Engine (RIE) ``guard-delta`` operation to
classify it, verifies the report, and projects a bounded advisory summary.

Authority boundary:
- RIE owns TIGHTENS/LOOSENS/MIXED/UNKNOWN/UNCHANGED. This module never computes
  a direction; it only forwards evidence and re-verifies the engine report.
- The engine is invoked as a subprocess from a pinned checkout
  (``NEXUS_RIE_ENGINE_ROOT`` / ``NEXUS_RIE_PYTHON_BIN``). It is never imported
  (see ``scripts/ops/canonical_owner_guard.py``).
- Output is advisory only: no required check, merge gate, policy decision,
  Candidate acceptance or completion authority. The only writes are the
  ``--output`` JSON artifact and the optional ``--step-summary`` markdown.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

PINNED_RIE_REVISION = "88285acf570688befbc8e36eb73f46987171bd4e"
ADVISORY_CLAIM_CEILING = "RIE_GUARD_SEMANTIC_DELTA_PR_REVIEW_ADVISORY_ONLY"
RIE_REPORT_SCHEMA = "reviewer.guard_semantic_delta.v1"
RIE_REPORT_CLAIM_CEILING = "GUARD_SEMANTIC_DELTA_ADVISORY_EVIDENCE_ONLY"
PROJECTION_SCHEMA = "nexus.rie_guard_semantic_delta_advisory.v1"

GUARD_FAMILY = "canonical_owner_table"
GUARD_SOURCE_PATH = "scripts/ops/canonical_owner_guard.py"
GUARD_SELF_TEST_PATH = "tests/ops/test_canonical_owner_guard.py"
OWNER_TABLE_NAME = "CANONICAL_OWNERS"

ENGINE_ROOT_ENV = "NEXUS_RIE_ENGINE_ROOT"
ENGINE_PYTHON_ENV = "NEXUS_RIE_PYTHON_BIN"

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@*+=-]{0,199}$")
MAX_LIST_ITEMS = 50
ENGINE_TIMEOUT_SECONDS = 60
PROBE_TIMEOUT_SECONDS = 30

# Read-only git subcommands. Anything else is refused: this lane has no mutation path.
_READ_ONLY_GIT = frozenset({"show", "rev-parse", "cat-file", "status"})

REVIEWER_ATTENTION = {
    "TIGHTENS": "INFORMATIONAL",
    "LOOSENS": "HIGH_SIGNAL_REVIEW_ATTENTION",
    "MIXED": "REVIEW_BOTH_DIRECTIONS",
    "UNKNOWN": "EXPLICIT_UNCERTAINTY_REQUIRES_REVIEW",
    "UNCHANGED": "NO_DIRECTIONAL_DELTA_OBSERVED",
}
AUTHORITY_STATEMENT = {
    "required_check": False,
    "merge_gate": False,
    "candidate_acceptance": False,
    "policy_owner": False,
}


class GuardDeltaEvidenceError(ValueError):
    """Raised when guard-delta evidence is malformed, stale, tampered or unverifiable."""


def canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_sha40(value: Any, name: str) -> str:
    text = str(value or "").strip().lower()
    if not SHA40.fullmatch(text):
        raise GuardDeltaEvidenceError(f"{name} must be a 40-character lowercase hex SHA")
    return text


def validate_identity(
    *,
    repository: str,
    pr_number: int,
    head_sha: str,
    base_sha: str,
    current_main_sha: str | None = None,
) -> dict[str, Any]:
    repo = str(repository or "").strip()
    if not repo or "/" not in repo:
        raise GuardDeltaEvidenceError("repository must be in owner/repo format")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        raise GuardDeltaEvidenceError("pr_number must be a positive integer")
    base = _validate_sha40(base_sha, "base_sha")
    return {
        "repository": repo,
        "pr_number": pr_number,
        "head_sha": _validate_sha40(head_sha, "head_sha"),
        "base_sha": base,
        "current_main_sha": _validate_sha40(current_main_sha or base, "current_main_sha"),
    }


# --------------------------------------------------------------------------- git


def _git(repo_root: Path, *args: str) -> bytes:
    if not args or args[0] not in _READ_ONLY_GIT:
        raise GuardDeltaEvidenceError(f"GIT_SUBCOMMAND_NOT_READ_ONLY:{args[:1]}")
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        timeout=60,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
    )
    if proc.returncode != 0:
        raise GuardDeltaEvidenceError(f"GIT_FAILED:{args[0]}")
    return proc.stdout


def git_show(repo_root: Path, revision: str, path: str) -> bytes:
    _validate_sha40(revision, "revision")
    return _git(repo_root, "show", f"{revision}:{path}")


def _commit_exists(repo_root: Path, sha: str) -> bool:
    try:
        _git(repo_root, "cat-file", "-e", f"{sha}^{{commit}}")
    except GuardDeltaEvidenceError:
        return False
    return True


# ------------------------------------------------------------- guard extraction


def extract_owner_table(source: bytes) -> tuple[dict[str, Any] | None, str | None]:
    """Deterministically normalize the declarative owner table.

    Only entries whose polarity is unambiguous are emitted:
    - ``owner:<name>``: an owner boundary exists (rule).
    - ``forbidden_import_stem:<owner>:<stem>`` and
      ``forwarding_module:<owner>:<path>``: enforced checks (bindings).
    ``allowed_retained_paths``, ``canonical_package`` and
    ``forwarding_reference_roots`` are exception/allow lists whose growth
    loosens the guard; they are deliberately NOT mapped (their changes surface
    as UNKNOWN via the implementation digest unless a behavioral witness exists).
    """
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None, "GUARD_SOURCE_UNPARSEABLE"
    table: Any = None
    found = False
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is not None and any(
            isinstance(t, ast.Name) and t.id == OWNER_TABLE_NAME for t in targets
        ):
            found = True
            try:
                table = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return None, "OWNER_TABLE_NOT_LITERAL"
    if not found:
        return None, "OWNER_TABLE_MISSING"
    if not isinstance(table, dict) or not all(
        isinstance(k, str) and isinstance(v, dict) for k, v in table.items()
    ):
        return None, "OWNER_TABLE_SHAPE_INVALID"

    rules: set[str] = set()
    bindings: set[str] = set()
    for owner, cfg in table.items():
        rules.add(f"owner:{owner}")
        for key, prefix in (
            ("forbidden_import_stems", "forbidden_import_stem"),
            ("forwarding_modules", "forwarding_module"),
        ):
            values = cfg.get(key, ())
            if not isinstance(values, (tuple, list)) or not all(
                isinstance(v, str) and v for v in values
            ):
                return None, "OWNER_TABLE_SHAPE_INVALID"
            bindings.update(f"{prefix}:{owner}:{v}" for v in values)
    docstring = ast.get_docstring(tree) or ""
    return {
        "rules": sorted(rules),
        "enforcement_bindings": sorted(bindings),
        "wording_sha256": _sha256_bytes(docstring.encode("utf-8")),
    }, None


# ---------------------------------------------------------- behavioral probes

_PROBE_RUNNER = r"""
import importlib.util, json, sys, tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("owner_guard_under_probe", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
owners = mod.CANONICAL_OWNERS

def fixture(root):
    first = None
    for cfg in owners.values():
        roots = tuple(cfg.get("forwarding_reference_roots", (cfg.get("canonical_package"),)))
        for rel in cfg.get("forwarding_modules", ()):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f'CANONICAL_IMPLEMENTATION_MODULE = "{roots[0]}"\n', encoding="utf-8")
            first = first or (p, roots[0])
    (root / "nexus").mkdir(exist_ok=True)
    return first

def decision(root, **kw):
    return "DENY" if mod.audit_repository_ownership(root, **kw)["status"] != "PASS" else "ALLOW"

stems = [s for cfg in owners.values() for s in cfg.get("forbidden_import_stems", ())]
out = {}
def fresh(fn):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        first = fixture(root)
        return fn(root, first)
out["control_clean_fixture"] = fresh(lambda r, f: decision(r))
def forbidden(r, f):
    (r / "nexus" / "probe.py").write_text(f"import {stems[0]}\n", encoding="utf-8")
    return decision(r)
def frozen(r, f):
    return decision(r, changed_files=["product/probe.py"])
def facade_missing(r, f):
    f[0].write_text("x = 1\n", encoding="utf-8")
    return decision(r)
def duplicate(r, f):
    f[0].write_text(f'CANONICAL_IMPLEMENTATION_MODULE = "{f[1]}"\nclass UnifiedRuntime:\n    pass\n', encoding="utf-8")
    return decision(r)
if stems:
    out["forbidden_import_in_nexus_tree"] = fresh(forbidden)
else:
    out["forbidden_import_in_nexus_tree"] = "ALLOW"
out["frozen_path_modification"] = fresh(frozen)
out["facade_without_canonical_reference"] = fresh(facade_missing)
out["facade_duplicate_canonical_class"] = fresh(duplicate)
print(json.dumps(out, sort_keys=True))
"""


def run_behavioral_probes(source: bytes) -> dict[str, str]:
    """Run fixed probe inputs against one guard source in an isolated subprocess."""
    with tempfile.TemporaryDirectory() as tmp:
        guard_file = Path(tmp) / "guard_under_probe.py"
        guard_file.write_bytes(source)
        proc = subprocess.run(
            [sys.executable, "-I", "-c", _PROBE_RUNNER, str(guard_file)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
            cwd=tmp,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        )
    if proc.returncode != 0:
        raise GuardDeltaEvidenceError("BEHAVIORAL_PROBE_RUNNER_FAILED")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GuardDeltaEvidenceError("BEHAVIORAL_PROBE_OUTPUT_INVALID") from exc
    if not isinstance(result, dict) or not all(v in {"ALLOW", "DENY"} for v in result.values()):
        raise GuardDeltaEvidenceError("BEHAVIORAL_PROBE_OUTPUT_INVALID")
    return result


def behavioral_witnesses(
    old_probes: Mapping[str, str], new_probes: Mapping[str, str]
) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    for side, probes in (("OLD", old_probes), ("NEW", new_probes)):
        if probes.get("control_clean_fixture") != "ALLOW":
            errors.append(f"{side}_PROBE_CONTROL_NOT_CLEAN")
    if set(old_probes) != set(new_probes):
        errors.append("PROBE_SET_MISMATCH")
    if errors:
        return [], errors
    return [
        {
            "witness_id": f"owner_guard_probe:{name}",
            "old_decision": old_probes[name],
            "new_decision": new_probes[name],
        }
        for name in sorted(old_probes)
        if name != "control_clean_fixture"
    ], []


# ------------------------------------------------------------------ collection


def _snapshot(identity: Mapping[str, Any], *, old: bool) -> dict[str, Any]:
    if old:
        sha = identity["base_sha"]
        return {
            "repository": identity["repository"],
            "pr_number": identity["pr_number"],
            "head_sha": sha,
            "base_sha": sha,
            "current_main_sha": sha,
            "declared_head_sha": sha,
            "declared_base_sha": sha,
            "declared_main_sha": sha,
        }
    return {
        "repository": identity["repository"],
        "pr_number": identity["pr_number"],
        "head_sha": identity["head_sha"],
        "base_sha": identity["base_sha"],
        "current_main_sha": identity["current_main_sha"],
        "declared_head_sha": identity["head_sha"],
        "declared_base_sha": identity["base_sha"],
        "declared_main_sha": identity["current_main_sha"],
    }


def _empty_guard() -> dict[str, Any]:
    return {
        "rules": [],
        "enforcement_bindings": [],
        "lifecycle_phases": [],
        "trigger_patterns": [],
        "fail_fixtures": [],
        "implementation_sha256": None,
        "self_test_sha256": None,
        "wording_sha256": None,
    }


def _collect_side(
    repo_root: Path, revision: str, label: str
) -> tuple[dict[str, Any], bytes | None, list[str]]:
    errors: list[str] = []
    guard = _empty_guard()
    source: bytes | None = None
    try:
        source = git_show(repo_root, revision, GUARD_SOURCE_PATH)
    except GuardDeltaEvidenceError:
        errors.append(f"{label}_GUARD_SOURCE_UNAVAILABLE")
    if source is not None:
        guard["implementation_sha256"] = _sha256_bytes(source)
        extracted, problem = extract_owner_table(source)
        if extracted is None:
            errors.append(f"{label}_{problem}")
        else:
            guard.update(extracted)
    try:
        guard["self_test_sha256"] = _sha256_bytes(
            git_show(repo_root, revision, GUARD_SELF_TEST_PATH)
        )
    except GuardDeltaEvidenceError:
        errors.append(f"{label}_SELF_TEST_UNAVAILABLE")
    return guard, source, errors


def collect_guard_delta_input(
    repo_root: Path,
    identity: Mapping[str, Any],
    *,
    run_probes: bool = False,
) -> dict[str, Any]:
    """Build the neutral ``guard-delta`` input from exact base/head blobs."""
    errors: list[str] = []
    for label, sha in (("BASE", identity["base_sha"]), ("HEAD", identity["head_sha"])):
        if not _commit_exists(repo_root, sha):
            raise GuardDeltaEvidenceError(f"{label}_COMMIT_NOT_FOUND")
    old_guard, old_src, old_err = _collect_side(repo_root, identity["base_sha"], "OLD")
    new_guard, new_src, new_err = _collect_side(repo_root, identity["head_sha"], "NEW")
    errors.extend(old_err + new_err)

    witnesses: list[dict[str, str]] = []
    if not run_probes:
        pass  # surfaced as an adapter gap in the projection, not as a collection failure
    elif old_src is None or new_src is None:
        errors.append("BEHAVIORAL_PROBES_SKIPPED_SOURCE_UNAVAILABLE")
    else:
        try:
            witnesses, probe_errors = behavioral_witnesses(
                run_behavioral_probes(old_src), run_behavioral_probes(new_src)
            )
            errors.extend(probe_errors)
        except (GuardDeltaEvidenceError, subprocess.SubprocessError, OSError) as exc:
            errors.append(f"BEHAVIORAL_PROBES_FAILED:{type(exc).__name__}")

    return {
        "old_snapshot": _snapshot(identity, old=True),
        "new_snapshot": _snapshot(identity, old=False),
        "old_guard": old_guard,
        "new_guard": new_guard,
        "known_files": sorted([GUARD_SELF_TEST_PATH, GUARD_SOURCE_PATH]),
        "behavioral_witnesses": witnesses,
        "collection_complete": not errors,
        "collection_errors": sorted(set(errors)),
    }


# ----------------------------------------------------------------------- engine


class SubprocessEngine:
    """Canonical RIE accessed only as a subprocess from a pinned, clean checkout."""

    def __init__(self, engine_root: str | Path, python_bin: str | Path):
        self.engine_root = Path(engine_root)
        self.python_bin = str(python_bin)

    def _env(self) -> dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(self.engine_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def verify_pin(self, pinned: str = PINNED_RIE_REVISION) -> str:
        if not self.engine_root.is_dir():
            raise GuardDeltaEvidenceError("ENGINE_ROOT_MISSING")
        try:
            head = _git(self.engine_root, "rev-parse", "HEAD").decode().strip().lower()
            dirty = _git(self.engine_root, "status", "--porcelain").strip()
        except (GuardDeltaEvidenceError, subprocess.SubprocessError, OSError) as exc:
            raise GuardDeltaEvidenceError("ENGINE_REVISION_UNVERIFIABLE") from exc
        if head != pinned:
            raise GuardDeltaEvidenceError("ENGINE_REVISION_MISMATCH")
        if dirty:
            raise GuardDeltaEvidenceError("ENGINE_CHECKOUT_DIRTY")
        return head

    def _run(self, args: Sequence[str], stdin: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.python_bin, *args],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=ENGINE_TIMEOUT_SECONDS,
                check=False,
                cwd=str(self.engine_root),
                env=self._env(),
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise GuardDeltaEvidenceError("ENGINE_INVOCATION_FAILED") from exc

    def analyze(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        proc = self._run(
            ["-m", "repository_intelligence.cli", "--operation", "guard-delta", "--input", "-"],
            json.dumps(payload, sort_keys=True),
        )
        if proc.returncode != 0:
            raise GuardDeltaEvidenceError("ENGINE_GUARD_DELTA_FAILED")
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise GuardDeltaEvidenceError("ENGINE_OUTPUT_MALFORMED") from exc
        if (
            not isinstance(envelope, dict)
            or envelope.get("operation") != "guard-delta"
            or not isinstance(envelope.get("result"), dict)
        ):
            raise GuardDeltaEvidenceError("ENGINE_OUTPUT_MALFORMED")
        return envelope["result"]

    def verify(self, report: Mapping[str, Any]) -> bool:
        code = (
            "import json,sys;"
            "from repository_intelligence.guard_delta import verify_guard_semantic_delta_report as v;"
            "print(json.dumps(bool(v(json.load(sys.stdin)))))"
        )
        proc = self._run(["-c", code], json.dumps(dict(report), sort_keys=True))
        return proc.returncode == 0 and proc.stdout.strip() == "true"


def engine_from_env(env: Mapping[str, str] | None = None) -> SubprocessEngine:
    env = os.environ if env is None else env
    root, python_bin = env.get(ENGINE_ROOT_ENV, ""), env.get(ENGINE_PYTHON_ENV, "")
    if not root or not python_bin:
        raise GuardDeltaEvidenceError("ENGINE_NOT_CONFIGURED")
    return SubprocessEngine(root, python_bin)


# ----------------------------------------------------------------- verification


def verify_report(
    report: Any,
    *,
    sent_input: Mapping[str, Any],
    identity: Mapping[str, Any],
    engine: Any,
) -> dict[str, Any]:
    """Fail closed unless the report is canonical, hash-bound, and bound to this base/head."""
    if not isinstance(report, Mapping):
        raise GuardDeltaEvidenceError("REPORT_NOT_OBJECT")
    if report.get("schema") != RIE_REPORT_SCHEMA:
        raise GuardDeltaEvidenceError("INVALID_REPORT_SCHEMA")
    if report.get("claim_ceiling") != RIE_REPORT_CLAIM_CEILING:
        raise GuardDeltaEvidenceError("INVALID_REPORT_CLAIM_CEILING")
    supplied = str(report.get("content_sha256") or "")
    if not SHA64.fullmatch(supplied):
        raise GuardDeltaEvidenceError("INVALID_REPORT_CONTENT_SHA256")
    if canonical_hash({k: v for k, v in report.items() if k != "content_sha256"}) != supplied:
        raise GuardDeltaEvidenceError("REPORT_CONTENT_SHA256_MISMATCH")
    if report.get("classification") not in REVIEWER_ATTENTION:
        raise GuardDeltaEvidenceError("INVALID_REPORT_CLASSIFICATION")

    # Exact old/new identity binding (stale or wrong base/head rejected).
    for key, old in (("old_identity", True), ("new_identity", False)):
        got = report.get(key)
        want = _snapshot(identity, old=old)
        if not isinstance(got, Mapping) or any(got.get(k) != v for k, v in want.items()):
            raise GuardDeltaEvidenceError(f"REPORT_{key.upper()}_MISMATCH")
        if got.get("stale_evidence"):
            raise GuardDeltaEvidenceError(f"REPORT_{key.upper()}_STALE")

    # The engine must have classified exactly the evidence we collected.
    for key in ("known_files", "behavioral_witnesses"):
        if json.loads(json.dumps(report.get(key))) != json.loads(json.dumps(sent_input[key])):
            raise GuardDeltaEvidenceError(f"REPORT_{key.upper()}_NOT_BOUND_TO_INPUT")
    for side in ("old_guard", "new_guard"):
        got, sent = report.get(side), sent_input[side]
        if (
            not isinstance(got, Mapping)
            or any(
                list(got.get(k) or []) != list(sent[k]) for k in ("rules", "enforcement_bindings")
            )
            or any(
                got.get(k) != sent[k]
                for k in ("implementation_sha256", "self_test_sha256", "wording_sha256")
            )
        ):
            raise GuardDeltaEvidenceError(f"REPORT_{side.upper()}_NOT_BOUND_TO_INPUT")

    if engine.verify(report) is not True:
        raise GuardDeltaEvidenceError("CANONICAL_VERIFIER_REJECTED_REPORT")
    return dict(report)


def _is_clean(report: Mapping[str, Any]) -> bool:
    return (
        report.get("is_complete") is True
        and report.get("collection_complete") is True
        and not report.get("evidence_gaps")
        and not report.get("collection_errors")
    )


# -------------------------------------------------------------------- projection


def _bounded_refs(values: Any) -> dict[str, Any]:
    items = [v for v in (values or []) if isinstance(v, str)]
    safe = [v if SAFE_REF.fullmatch(v) else "[NON_IDENTIFIER_REDACTED]" for v in items]
    return {
        "items": safe[:MAX_LIST_ITEMS],
        "total": len(safe),
        "truncated": len(safe) > MAX_LIST_ITEMS,
    }


def _identity_summary(identity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: identity[k]
        for k in ("repository", "pr_number", "head_sha", "base_sha", "current_main_sha")
    }


def _seal(body: dict[str, Any]) -> dict[str, Any]:
    body["content_sha256"] = canonical_hash({
        k: v for k, v in body.items() if k != "content_sha256"
    })
    return body


def project_report(
    report: Mapping[str, Any],
    identity: Mapping[str, Any],
    engine_revision: str,
    adapter_gaps: Sequence[str] = (),
) -> dict[str, Any]:
    """Bounded advisory projection of a VERIFIED report. No source/policy text is copied."""
    classification = str(report["classification"])
    if classification == "UNCHANGED" and not _is_clean(report):
        # Defense in depth: incomplete evidence may never read as "unchanged".
        classification = "UNKNOWN"
    return _seal({
        "schema": PROJECTION_SCHEMA,
        "disposition": "OBSERVED",
        "guard_family": GUARD_FAMILY,
        "classification": classification,
        "reviewer_attention": REVIEWER_ATTENTION[classification],
        "reason_codes": _bounded_refs(report.get("reason_codes")),
        "tightening_witnesses": _bounded_refs(report.get("tightening_witnesses")),
        "loosening_witnesses": _bounded_refs(report.get("loosening_witnesses")),
        "evidence_gaps": _bounded_refs(report.get("evidence_gaps")),
        "collection_errors": _bounded_refs(report.get("collection_errors")),
        "adapter_gaps": _bounded_refs(list(adapter_gaps)),
        "evidence_complete": _is_clean(report) and not adapter_gaps,
        "report_content_sha256": report["content_sha256"],
        "engine_revision": engine_revision,
        "old_identity": _identity_summary(report["old_identity"]),
        "new_identity": _identity_summary(report["new_identity"]),
        "authority": dict(AUTHORITY_STATEMENT),
        "claim_ceiling": ADVISORY_CLAIM_CEILING,
    })


def make_incomplete_projection(identity: Mapping[str, Any], reason: str) -> dict[str, Any]:
    """Absent/unverifiable report: classification is NOT_OBSERVED, never UNCHANGED."""
    code = reason if SAFE_REF.fullmatch(reason) else "UNSPECIFIED"
    return _seal({
        "schema": PROJECTION_SCHEMA,
        "disposition": "ADVISORY_INCOMPLETE",
        "guard_family": GUARD_FAMILY,
        "classification": "NOT_OBSERVED",
        "reviewer_attention": "EXPLICIT_UNCERTAINTY_REQUIRES_REVIEW",
        "reason": code,
        "evidence_complete": False,
        "old_identity": {**_identity_summary(identity), "head_sha": identity["base_sha"]},
        "new_identity": _identity_summary(identity),
        "authority": dict(AUTHORITY_STATEMENT),
        "claim_ceiling": ADVISORY_CLAIM_CEILING,
    })


def render_step_summary(projection: Mapping[str, Any]) -> str:
    lines = [
        "## RIE Guard Semantic Delta (advisory)",
        "",
        f"- Guard family: `{projection['guard_family']}`",
        f"- Disposition: `{projection['disposition']}`",
        f"- Classification: `{projection['classification']}`",
        f"- Reviewer attention: `{projection['reviewer_attention']}`",
        f"- Evidence complete: `{projection['evidence_complete']}`",
    ]
    new, old = projection["new_identity"], projection["old_identity"]
    lines += [
        f"- Old identity: `{old['repository']}` `{old['head_sha']}`",
        f"- New identity: `{new['repository']}` PR `{new['pr_number']}` head `{new['head_sha']}` "
        f"base `{new['base_sha']}` main `{new['current_main_sha']}`",
    ]
    if projection["disposition"] == "OBSERVED":
        lines.append(f"- RIE report SHA-256: `{projection['report_content_sha256']}`")
        lines.append(f"- RIE revision: `{projection['engine_revision']}`")
        for title, key in (
            ("Reason codes", "reason_codes"),
            ("Tightening witnesses", "tightening_witnesses"),
            ("Loosening witnesses", "loosening_witnesses"),
            ("Evidence gaps", "evidence_gaps"),
            ("Collection errors", "collection_errors"),
            ("Adapter gaps", "adapter_gaps"),
        ):
            block = projection[key]
            lines += ["", f"### {title} ({block['total']})"]
            lines += [f"- `{item}`" for item in block["items"]] or ["- none"]
            if block["truncated"]:
                lines.append(
                    f"- ... truncated, {block['total'] - len(block['items'])} more in artifact"
                )
    else:
        lines.append(f"- Reason: `{projection['reason']}`")
        lines.append("- No guard delta was observed or verified; this is NOT an unchanged result.")
    lines += [
        "",
        f"Claim ceiling: `{projection['claim_ceiling']}`",
        "",
        "Advisory evidence only. It is not a required check, merge gate, policy decision "
        "or Candidate acceptance. LOOSENS is a review-attention signal, not a rejection.",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ orchestration


def generate_advisory(
    *,
    repo_root: Path,
    identity: Mapping[str, Any],
    engine: Any,
    run_probes: bool = False,
) -> dict[str, Any]:
    """Collect, classify (via RIE), verify and project. Failures yield ADVISORY_INCOMPLETE."""
    try:
        engine_revision = engine.verify_pin()
        payload = collect_guard_delta_input(repo_root, identity, run_probes=run_probes)
        report = verify_report(
            engine.analyze(payload), sent_input=payload, identity=identity, engine=engine
        )
        gaps = [] if run_probes else ["BEHAVIORAL_PROBES_NOT_RUN"]
        return project_report(report, identity, engine_revision, gaps)
    except GuardDeltaEvidenceError as exc:
        return make_incomplete_projection(identity, str(exc).split(":")[0].replace(" ", "_"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--current-main-sha", default="")
    parser.add_argument("--engine-root", default=os.environ.get(ENGINE_ROOT_ENV, ""))
    parser.add_argument("--python-bin", default=os.environ.get(ENGINE_PYTHON_ENV, ""))
    parser.add_argument(
        "--run-behavioral-probes",
        action="store_true",
        help="Execute fixed probes against base/head guard source in an isolated subprocess (opt-in).",
    )
    parser.add_argument("--output", default="rie-guard-semantic-delta.json")
    parser.add_argument("--step-summary", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        identity = validate_identity(
            repository=args.repository,
            pr_number=args.pr_number,
            head_sha=args.head_sha,
            base_sha=args.base_sha,
            current_main_sha=args.current_main_sha,
        )
    except GuardDeltaEvidenceError as exc:
        print(
            json.dumps(
                {"status": "ERROR", "reason": str(exc), "claim_ceiling": ADVISORY_CLAIM_CEILING},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    try:
        engine: Any = engine_from_env({
            ENGINE_ROOT_ENV: args.engine_root,
            ENGINE_PYTHON_ENV: args.python_bin,
        })
        projection = generate_advisory(
            repo_root=Path(args.repo_root),
            identity=identity,
            engine=engine,
            run_probes=args.run_behavioral_probes,
        )
    except GuardDeltaEvidenceError as exc:
        projection = make_incomplete_projection(identity, str(exc))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.step_summary:
        Path(args.step_summary).write_text(render_step_summary(projection), encoding="utf-8")
    print(json.dumps(projection, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
