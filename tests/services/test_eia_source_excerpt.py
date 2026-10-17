"""Symbol-sliced excerpts for oversized Python contract sources (#2357 step 2a)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from nexus.services.eia_source_excerpt import (
    EXCERPT_SCHEMA,
    ExcerptError,
    build_python_excerpt,
)
from nexus.services.external_intelligence import (
    DEFAULT_CONTEXT_BUDGET,
    ExternalIntelligenceError,
    bind_contract_evidence_refs,
    build_context_pack,
    compute_evidence_ref,
    validate_context_pack,
)
from nexus.services.external_intelligence_automation import (
    AutomationError,
    parse_issue_contract,
)
from tests.services.test_external_intelligence_automation import (
    FakeSidecar,
    _automation,
    _body,
    _contract,
    _setup,
    _sha,
)

REV = "a" * 40


def _big_module() -> str:
    """A >200 KB module: imports, many filler functions, a class and a target."""
    parts = [
        '"""Synthetic large module."""\n',
        "import os\n",
        "from typing import Any\n\n",
        "CONSTANT = 1\n\n",
    ]
    for i in range(1500):
        parts.append(
            f"def filler_{i}(value: Any) -> Any:\n"
            f"    marker = 'FILLER_BODY_{i}'\n"
            f"    return (value, marker, {i}, os.sep, 'padding padding padding padding')\n\n"
        )
    parts.append(
        "class Big:\n"
        "    def other(self):\n"
        "        return 'OTHER_METHOD_BODY'\n\n"
        "    @staticmethod\n"
        "    def method(x):\n"
        "        return 'METHOD_BODY_MARKER' + str(x)\n\n"
    )
    parts.append("def target(x):\n    return 'TARGET_BODY_MARKER' + str(x)\n")
    text = "".join(parts)
    assert len(text.encode("utf-8")) > DEFAULT_CONTEXT_BUDGET
    return text


def _src(kind, ref, content, **extra):
    return {
        "kind": kind,
        "ref": ref,
        "revision": REV,
        "provenance": f"git:{REV}",
        "content": content,
        **extra,
    }


def _pack(content, symbols=None, ref="nexus/big.py"):
    extra = {} if symbols is None else {"excerpt_symbols": symbols}
    return build_context_pack([
        _src("task_card", "tasks/t.md", "# card\n"),
        _src("source_file", ref, content, **extra),
    ])


def test_oversized_py_source_gets_hash_index_and_named_slices_only():
    content = _big_module()
    pack = _pack(content, ["target", "Big.method"])
    entry = next(e for e in pack["entries"] if e["kind"] == "source_file")
    full_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

    assert entry["source_sha256"] == full_sha
    assert entry["source_bytes"] == len(content.encode("utf-8"))
    assert entry["truncated"] is True
    assert entry["included_bytes"] < DEFAULT_CONTEXT_BUDGET
    text = entry["content"]
    assert "NOT THE WHOLE FILE" in text
    assert f"# full_file_sha256: {full_sha}\n" in text
    assert "import os\n" in text and "from typing import Any\n" in text
    # Index lists every top-level symbol and class method with line ranges.
    assert "- filler_0 | def | " in text
    assert "- filler_1499 | def | " in text
    assert "- Big | class | " in text
    assert "- Big.other | def | " in text
    assert "- CONSTANT | assign | " in text
    # Named slices are present in full, labelled with their line range.
    meta = entry["excerpt"]
    assert meta["schema"] == EXCERPT_SCHEMA
    assert meta["symbols"] == ["Big.method", "target"]
    by_name = {s["name"]: s for s in meta["slices"]}
    lines = content.splitlines(keepends=True)
    for name in ("target", "Big.method"):
        s = by_name[name]
        header = f"## SLICE {name} ({s['kind']}) lines {s['start_line']}-{s['end_line']}\n"
        assert header in text
        assert "".join(lines[s["start_line"] - 1 : s["end_line"]]) in text
    assert "@staticmethod" in text  # decorator belongs to the slice
    assert "TARGET_BODY_MARKER" in text and "METHOD_BODY_MARKER" in text
    # No other bodies.
    assert "FILLER_BODY_" not in text
    assert "OTHER_METHOD_BODY" not in text
    # The pack still validates and its evidence anchor binds the whole file.
    assert validate_context_pack(pack) == pack
    assert entry["evidence_ref"] == compute_evidence_ref(entry)
    forged = {**entry, "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    assert compute_evidence_ref(forged) != entry["evidence_ref"]


def test_bound_envelope_refs_carry_the_full_file_anchor_for_excerpts():
    pack = _pack(_big_module(), ["target"])
    entry = next(e for e in pack["entries"] if e["kind"] == "source_file")
    envelope = {"schema": "external_execution_envelope.v2", "evidence_refs": []}
    bound = bind_contract_evidence_refs(envelope, pack)
    assert entry["evidence_ref"] in bound["evidence_refs"]


def test_oversized_py_source_without_symbol_scope_fails_closed():
    with pytest.raises(ExternalIntelligenceError, match="^CONTRACT_CONTEXT_BUDGET_EXCEEDED$"):
        _pack(_big_module())


def test_oversized_non_python_source_fails_closed_even_with_symbols():
    with pytest.raises(ExternalIntelligenceError, match="CONTRACT_EXCERPT_UNSUPPORTED_SOURCE"):
        _pack("x" * (DEFAULT_CONTEXT_BUDGET + 10), ["target"], ref="docs/big.md")


def test_unknown_symbol_fails_closed():
    with pytest.raises(ExternalIntelligenceError, match="CONTRACT_EXCERPT_SYMBOL_NOT_FOUND"):
        _pack(_big_module(), ["does_not_exist"])


def test_unparsable_oversized_source_fails_closed():
    broken = "def broken(:\n" + "#" * (DEFAULT_CONTEXT_BUDGET + 10) + "\n"
    with pytest.raises(ExternalIntelligenceError, match="CONTRACT_EXCERPT_PARSE_FAILED"):
        _pack(broken, ["broken"])


def test_excerpt_still_over_total_budget_fails_closed():
    content = _big_module()
    many = [f"filler_{i}" for i in range(0, 1500, 25)]  # 60 slices
    with pytest.raises(ExternalIntelligenceError, match="CONTRACT_CONTEXT_BUDGET_EXCEEDED"):
        build_context_pack(
            [_src("source_file", "nexus/big.py", content, excerpt_symbols=many)],
            max_bytes=8_000,
            per_source_bytes=8_000,
        )


def test_small_source_with_symbol_scope_is_unchanged():
    content = "import os\n\ndef target():\n    return os.sep\n"
    with_scope = _pack(content, ["target"])
    without = _pack(content)
    assert with_scope == without
    entry = next(e for e in with_scope["entries"] if e["kind"] == "source_file")
    assert entry["content"] == content
    assert entry["truncated"] is False
    assert "excerpt" not in entry


def test_excerpt_symbols_rejected_on_non_source_file_kind():
    with pytest.raises(ExternalIntelligenceError, match="INVALID_CONTEXT_SOURCE"):
        build_context_pack([_src("task_card", "tasks/t.md", "c", excerpt_symbols=["x"])])


def test_validator_rejects_excerpt_entry_that_does_not_declare_itself():
    pack = _pack(_big_module(), ["target"])
    tampered = json.loads(json.dumps(pack))
    for entry in tampered["entries"]:
        if "excerpt" in entry:
            entry["truncated"] = False
    from nexus.services import external_intelligence as ei

    material = {k: tampered[k] for k in ("schema", "max_bytes", "per_source_bytes", "entries")}
    tampered["context_pack_sha256"] = ei._sha256(ei._canonical_json(material))
    with pytest.raises(ExternalIntelligenceError, match="INVALID_CONTEXT_PACK"):
        validate_context_pack(tampered)


def test_build_python_excerpt_requires_symbols():
    with pytest.raises(ExcerptError, match="CONTRACT_EXCERPT_NO_SYMBOL_SCOPE"):
        build_python_excerpt("a.py", "x = 1\n", [], full_file_sha256="0" * 64)


@pytest.mark.parametrize(
    "scope",
    [
        {"nexus/other.py": ["target"]},  # not a mutation path of the unit
        {"nexus/a.py": []},
        {"nexus/a.py": ["bad-name"]},
        {"nexus/a.py": "target"},
        [],
        {"tests/test_a.py": ["x"]},  # belongs to another unit
    ],
)
def test_contract_rejects_invalid_excerpt_symbols(tmp_path, scope):
    _, card, contract, _, _ = _setup(tmp_path)
    contract["execution_units"][0]["excerpt_symbols"] = scope
    with pytest.raises(AutomationError, match="ISSUE_CONTRACT_UNIT_EXCERPT_SYMBOLS_INVALID"):
        parse_issue_contract(_body(contract))


def test_automation_runs_oversized_py_mutation_path_with_named_symbols(tmp_path):
    repo, card, _, _, store = _setup(tmp_path)
    big = repo / "nexus" / "a.py"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_text(_big_module(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "big"], cwd=repo, capture_output=True, check=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", head_sha],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    contract = _contract("tasks/x.md", _sha(card), main_sha=head_sha)
    contract["execution_units"][0]["excerpt_symbols"] = {"nexus/a.py": ["target"]}
    sidecar = FakeSidecar(store)
    automation = _automation(tmp_path, repo, store, sidecar=sidecar)

    result = automation.run_issue("o/r", 2357, "title", _body(contract))

    assert result["state"] != "BLOCKED", result
    assert len(sidecar.calls) == 1
    sources = sidecar.calls[0][1]
    big_source = next(s for s in sources if s["ref"] == "nexus/a.py")
    assert big_source["excerpt_symbols"] == ["target"]
    entry = next(e for e in build_context_pack(sources)["entries"] if e["ref"] == "nexus/a.py")
    assert entry["source_sha256"] == hashlib.sha256(Path(big).read_bytes()).hexdigest()
    assert entry["excerpt"]["symbols"] == ["target"]


def test_automation_without_symbol_scope_still_blocks_oversized_source(tmp_path):
    repo, card, _, _, store = _setup(tmp_path)
    big = repo / "nexus" / "a.py"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_text(_big_module(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "big"], cwd=repo, capture_output=True, check=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", head_sha],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    contract = _contract("tasks/x.md", _sha(card), main_sha=head_sha)
    sidecar = FakeSidecar(store)
    automation = _automation(tmp_path, repo, store, sidecar=sidecar)

    result = automation.run_issue("o/r", 2357, "title", _body(contract))

    assert result["state"] == "BLOCKED"
    assert sidecar.calls == []


def test_fanout_units_carry_whole_file_hash_only_for_excerpted_paths(tmp_path):
    from tests.services.test_external_intelligence_automation import FakeC

    repo, card, _, _, store = _setup(tmp_path)
    big = repo / "nexus" / "a.py"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_text(_big_module(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "big"], cwd=repo, capture_output=True, check=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", head_sha],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    contract = _contract("tasks/x.md", _sha(card), main_sha=head_sha)
    contract["execution_units"][0]["excerpt_symbols"] = {"nexus/a.py": ["target"]}
    c = FakeC()
    automation = _automation(tmp_path, repo, store, c=c)

    automation.run_issue("o/r", 2357, "title", _body(contract))

    units = {u["unit_id"]: u for u in c.calls[0][0]}
    assert units["u1"]["excerpt_base_hashes"] == {
        "nexus/a.py": hashlib.sha256(big.read_bytes()).hexdigest()
    }
    assert "excerpt_base_hashes" not in units["u2"]


def test_fanout_units_have_no_excerpt_hash_when_source_fit_whole(tmp_path):
    from tests.services.test_external_intelligence_automation import FakeC

    repo, card, _, _, store = _setup(tmp_path)
    small = repo / "nexus" / "a.py"
    small.parent.mkdir(parents=True, exist_ok=True)
    small.write_text("def target():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "small"], cwd=repo, capture_output=True, check=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", head_sha],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    contract = _contract("tasks/x.md", _sha(card), main_sha=head_sha)
    contract["execution_units"][0]["excerpt_symbols"] = {"nexus/a.py": ["target"]}
    c = FakeC()
    automation = _automation(tmp_path, repo, store, c=c)

    automation.run_issue("o/r", 2357, "title", _body(contract))

    assert all("excerpt_base_hashes" not in u for u in c.calls[0][0])
