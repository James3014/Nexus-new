"""CodeIntel relevance-ranked retrieval core (#2640)."""

from __future__ import annotations

from pathlib import Path

from nexus.services.codeintel.retrieval import (
    PATH_BOOST,
    build_code_retrieval_index,
    extract_query_identifiers,
    rank_files,
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    _write(tmp_path, "aaa/hello.py", "print('hello world')\n")
    _write(tmp_path, "nexus/memory/store.py", "def search_cards(query):\n    return []\n")
    _write(
        tmp_path,
        "nexus/memory/user.py",
        "from nexus.memory.store import search_cards\n\nsearch_cards('x')\n",
    )
    _write(
        tmp_path,
        "nexus/gateway/deploy.py",
        "def deploy_gateway():\n    return 'deploy gateway now'\n",
    )
    _write(tmp_path, ".nexus/reports/x.py", "def search_cards():\n    pass\n")
    return tmp_path


def test_rank_files_ranks_by_relevance_not_walk_order(tmp_path):
    root = _repo(tmp_path)
    ranked = rank_files(root, "Gateway deploy fails when deploying the gateway")
    assert ranked[0].path == "nexus/gateway/deploy.py"
    assert "aaa/hello.py" not in [item.path for item in ranked]  # no relevance, not returned


def test_symbol_definition_boost_prefers_defining_file(tmp_path):
    root = _repo(tmp_path)
    ranked = rank_files(root, "`search_cards` returns nothing")
    assert ranked[0].path == "nexus/memory/store.py"
    assert ranked[0].boosts.get("symbol", 0) > 0
    assert "nexus/memory/user.py" in [item.path for item in ranked]


def test_path_named_in_query_is_boosted(tmp_path):
    root = _repo(tmp_path)
    ranked = rank_files(root, "hello.py prints the wrong greeting")
    assert ranked[0].path == "aaa/hello.py"
    assert ranked[0].boosts["path"] == PATH_BOOST


def test_impact_boost_only_reorders_existing_candidates(tmp_path):
    root = _repo(tmp_path)
    ranked = {item.path: item for item in rank_files(root, "search_cards query")}
    assert ranked["nexus/memory/user.py"].boosts.get("impact", 0) > 0
    assert "nexus/gateway/deploy.py" not in ranked


def test_state_dirs_are_not_indexed(tmp_path):
    root = _repo(tmp_path)
    assert all(not item.path.startswith(".nexus/") for item in rank_files(root, "search_cards"))


def test_index_cache_refreshes_when_a_file_changes(tmp_path):
    root = _repo(tmp_path)
    first = build_code_retrieval_index(root)
    assert build_code_retrieval_index(root) is first
    _write(
        root,
        "nexus/memory/store.py",
        "def search_cards(query):\n    return ['changed and longer']\n",
    )
    assert build_code_retrieval_index(root) is not first


def test_extract_query_identifiers():
    ids = extract_query_identifiers(
        "Fix `retry` in ./nexus/a/b.py via nexus.a.b and FooBar plus MAX_SIZE"
    )
    assert ids["paths"] == ["nexus/a/b.py"]
    assert "nexus.a.b" in ids["dotted"]
    assert {"retry", "FooBar", "MAX_SIZE"} <= set(ids["symbols"])
