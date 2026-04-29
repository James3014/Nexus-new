from nexus.engine.ddtree_adapter import DDTreeAdapter


def test_ddtree_prunes_candidate_set_when_enabled():
    out = DDTreeAdapter().plan(
        [
            {"candidate_id": "a", "score": 0.1},
            {"candidate_id": "b", "score": 0.8, "evidence_refs": ["pytest.log"]},
            {"candidate_id": "c", "score": 0.5},
        ],
        enabled=True,
        max_candidates=2,
    )

    assert out["schema"] == "nexus_ddtree_plan_v2"
    assert out["eligible"] is True
    assert out["selected_candidate_ids"] == ["b", "c"]
    assert out["actual_saved_steps"] == 1
    assert out["pruning_mode"] == "tree"
    assert out["root_node_id"] == "root"
    assert out["tree_stats"] == {
        "max_depth": 1,
        "branch_count": 3,
        "leaf_count": 3,
        "pruned_count": 1,
    }
    assert out["prune_events"] == [
        {
            "node_id": "root",
            "depth": 0,
            "input_candidate_ids": ["a", "b", "c"],
            "kept_candidate_ids": ["b", "c"],
            "pruned_candidate_ids": ["a"],
            "criterion": "score_then_evidence",
        }
    ]


def test_ddtree_is_observable_but_noop_when_disabled():
    out = DDTreeAdapter().plan(
        [{"candidate_id": "a"}, {"candidate_id": "b"}, {"candidate_id": "c"}],
        enabled=False,
        max_candidates=2,
    )

    assert out["enabled"] is False
    assert out["eligible"] is True
    assert out["selected_candidate_ids"] == ["a", "b", "c"]
    assert out["reason"] == "disabled"
