from nexus.contracts.retrieval_query import build_retrieval_query


def test_retrieval_query_normalizes_safe_text() -> None:
    query = build_retrieval_query("  websocket\n timeout   race  ", source_scope="doc_scout")

    assert query.normalized_text == "websocket timeout race"
    assert query.receipt()["status"] == "PASS"
    assert query.receipt()["query_allowed"] is True


def test_retrieval_query_flags_control_chars() -> None:
    query = build_retrieval_query("safe\x00unsafe", source_scope="doc_scout")

    receipt = query.receipt()
    assert receipt["status"] == "RETURN"
    assert receipt["unsafe_flags"] == ["control_chars"]


def test_retrieval_query_flags_truncation() -> None:
    query = build_retrieval_query("abcdef", source_scope="doc_scout", max_chars=3)

    receipt = query.receipt()
    assert query.normalized_text == "abc"
    assert receipt["status"] == "RETURN"
    assert "query_truncated" in receipt["unsafe_flags"]
