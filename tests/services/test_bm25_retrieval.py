"""Shared BM25 scorer (#2640): tokenizer and formula match the #2626 PREREG baseline."""

from __future__ import annotations

import math

from nexus.services.bm25_retrieval import BM25Index, bm25_rank, bm25_tokens


def test_tokenizer_keeps_whole_token_and_snake_and_camel_parts():
    assert bm25_tokens("resolve_lancedb_root") == [
        "resolve_lancedb_root",
        "resolve",
        "lancedb",
        "root",
    ]
    assert bm25_tokens("FindingsMemoryStore") == [
        "findingsmemorystore",
        "findings",
        "memory",
        "store",
    ]
    # a single part equal to the whole token is not duplicated; parts shorter than 3 are dropped
    assert bm25_tokens("search") == ["search"]
    assert bm25_tokens("a_bc_def") == ["a_bc_def", "def"]


def test_idf_is_non_negative_lucene_form_and_scores_match_okapi():
    docs = [("a", "alpha beta"), ("b", "alpha gamma gamma"), ("c", "delta")]
    index = BM25Index(docs)
    n, df = 3, 2
    idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
    avg = (2 + 3 + 1) / 3
    expected_a = idf * 1 * 2.2 / (1 + 1.2 * (1 - 0.75 + 0.75 * 2 / avg))
    scores = index.scores("alpha")
    assert math.isclose(scores[0], expected_a, rel_tol=1e-12)
    assert 2 not in scores  # zero-score documents are not returned


def test_rank_orders_by_score_then_insertion_order():
    docs = [
        ("x.py", "memory store"),
        ("a.py", "memory store"),
        ("m.py", "memory memory store retrieval"),
    ]
    ranked = bm25_rank(docs, "memory retrieval")
    assert [doc for doc, _ in ranked][0] == "m.py"
    assert [doc for doc, _ in ranked][1:] == ["x.py", "a.py"]
    assert bm25_rank(docs, "memory", limit=1)[0][0] == "m.py"


def test_multi_word_sentence_matches_on_shared_words():
    docs = [(0, "lancedb search falls back to substring"), (1, "unrelated gateway deploy")]
    ranked = bm25_rank(docs, "The LanceDB fallback search never matched any row")
    assert [doc for doc, _ in ranked] == [0]


def test_empty_corpus_and_empty_query():
    assert BM25Index([]).rank("anything") == []
    assert BM25Index([(1, "text")]).rank("") == []


def test_floor_needs_two_informative_terms_for_a_sentence():
    docs = [(0, "websocket reconnect timeout"), (1, "websocket only"), (2, "unrelated words here")]
    index = BM25Index(docs)
    assert set(index.floored_scores("websocket timeout in the coordinator")) == {0}
    assert set(index.floored_scores("websocket")) == {0, 1}  # one-word query needs its word


def test_floor_ignores_stopwords_and_terms_most_documents_share():
    docs = [(i, f"LocalHeal lesson memory trace nexus card {i}") for i in range(10)]
    docs.append((10, "gateway deploy restarts"))
    index = BM25Index(docs)
    assert "the" not in index.informative_terms("the gateway")
    assert "memory" not in index.informative_terms("memory gateway")  # in 10 of 11 documents
    # every card shares "memory"/"nexus": a generic sentence matches none of them
    assert index.floored_scores("Fix the failing test in nexus/services/memory.py") == {}
    assert index.floored_scores("the of and") == {}
    assert set(index.floored_scores("gateway deploy")) == {10}
