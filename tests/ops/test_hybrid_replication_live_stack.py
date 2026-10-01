from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.ops.hybrid_replication_live_stack import (
    build_d0_packet,
    build_jev_request,
    classify_shadow_stratum,
    d2_project_packet,
    execute_effect_once,
    parse_codex_usage,
    parse_jev_response,
)


def test_natural_mutation_task_routes_conservatively_to_c() -> None:
    assert (
        classify_shadow_stratum(
            title="P1 Governance: repair admission contract",
            body="Modify the bounded source and tests. No route authority change.",
        )
        == "C"
    )


def test_explicit_finite_candidate_ranking_routes_to_b() -> None:
    assert (
        classify_shadow_stratum(
            title="Rank the supplied candidate files",
            body=(
                "Choose the ONE supplied candidate file most likely to require modification. "
                "Use only supplied candidate IDs."
            ),
        )
        == "B"
    )


def test_d2_projection_preserves_final_candidate_records() -> None:
    packet = {
        "schema": "nexus.hybrid_economics_r3.deterministic_packet.v2",
        "retriever": "D0_V2_FROZEN",
        "freeze_sha256": "a" * 64,
        "implementation_sha256": "b" * 64,
        "execution_start_base": "c" * 40,
        "issue": 99,
        "query_projection": {"tokens": ["noise"]},
        "literal_task_paths": ["nexus/example.py"],
        "d0_v2_original_candidates": [{"path": "nexus/example.py"}],
        "candidates": [
            {
                "path": "nexus/example.py",
                "source": "LITERAL_TASK_PATH",
                "evidence": ["literal_path_in_issue_body"],
                "packet_rank": 1,
            }
        ],
    }

    projected = d2_project_packet(packet)

    assert projected["candidates"] == packet["candidates"]
    assert projected["literal_task_paths"] == packet["literal_task_paths"]
    assert "query_projection" not in projected
    assert "d0_v2_original_candidates" not in projected


def test_codex_usage_uses_machine_readable_turn_completed(tmp_path: Path) -> None:
    events = tmp_path / "codex.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 30,
                            "cache_write_input_tokens": 0,
                            "output_tokens": 12,
                            "reasoning_output_tokens": 4,
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    usage = parse_codex_usage(events)

    assert usage["input_tokens"] == 100
    assert usage["uncached_input_tokens"] == 70
    assert usage["output_tokens"] == 12
    assert usage["turns"] == 1



def test_build_d0_packet_reuses_hash_bound_external_donor(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "nexus").mkdir()
    (repo / "nexus" / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    donor = tmp_path / "donor"
    donor.mkdir()
    impl = donor / "d0_v2_develop.py"
    impl.write_text(
        "REPO = None\n"
        "def rank_task(rev, statement, weights):\n"
        "    return ['nexus/target.py'], {'nexus/target.py': 9.0}, "
        "{'nexus/target.py': ['exact_identifier:target']}, {'tokens': ['target']}\n",
        encoding="utf-8",
    )
    impl_sha = hashlib.sha256(impl.read_bytes()).hexdigest()
    freeze = donor / "D0_V2_FROZEN.json"
    freeze.write_text(
        json.dumps(
            {
                "implementation_sha256": impl_sha,
                "weights": {"name": "test"},
                "candidate_budget_k": 8,
            }
        ),
        encoding="utf-8",
    )

    packet = build_d0_packet(
        repository_root=repo,
        donor_root=donor,
        issue_number=77,
        title="Locate target",
        body="Inspect nexus/target.py and choose the candidate.",
        revision=revision,
    )

    assert packet["retriever"] == "D0_V2_FROZEN"
    assert packet["implementation_sha256"] == impl_sha
    assert packet["literal_task_paths"] == ["nexus/target.py"]
    assert packet["candidates"][0]["path"] == "nexus/target.py"


def test_build_d0_packet_rejects_donor_hash_drift(tmp_path: Path) -> None:
    donor = tmp_path / "donor"
    donor.mkdir()
    (donor / "d0_v2_develop.py").write_text("def rank_task(*a): return []\n", encoding="utf-8")
    (donor / "D0_V2_FROZEN.json").write_text(
        json.dumps(
            {
                "implementation_sha256": "0" * 64,
                "weights": {},
                "candidate_budget_k": 8,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="d0_implementation_hash_mismatch"):
        build_d0_packet(
            repository_root=tmp_path,
            donor_root=donor,
            issue_number=1,
            title="x",
            body="x",
            revision="deadbeef",
        )



def test_jev_request_uses_only_packet_candidate_ids() -> None:
    packet = {
        "candidates": [
            {"id": "C1", "path": "nexus/a.py", "source": "D0_V2_FROZEN", "evidence": ["x"]},
            {"id": "C2", "path": "nexus/b.py", "source": "D0_V2_FROZEN", "evidence": ["y"]},
        ],
        "execution_start_base": "a" * 40,
        "issue": 55,
    }
    request = build_jev_request(
        packet=packet,
        task_contract_text="Choose one supplied candidate file.",
        task_identity="James3014/Nexus-new#55",
    )
    criteria = request["questions"]["file_choice"]["criteria"]
    assert set(criteria) == {"C1", "C2", "ESCALATE"}
    assert request["model"] == "jev-latest"


def test_parse_jev_response_validates_probability_contract_and_records_model() -> None:
    parsed = parse_jev_response(
        {
            "model": "jev-1.14.0",
            "answers": {
                "file_choice": {
                    "type": "choice",
                    "choice": "C1",
                    "confidence": 0.8,
                    "probabilities": {"C1": 0.8, "C2": 0.1, "ESCALATE": 0.1},
                }
            },
            "usage": {"input_tokens": 50, "output_tokens": 7},
        },
        criteria={"C1", "C2", "ESCALATE"},
    )
    assert parsed["status"] == "VALID"
    assert parsed["resolved_model"] == "jev-1.14.0"
    assert parsed["top_probability"] == 0.8
    assert parsed["margin"] == pytest.approx(0.7)


def test_parse_jev_response_rejects_incomplete_probability_set() -> None:
    parsed = parse_jev_response(
        {
            "model": "jev-1.14.0",
            "answers": {
                "file_choice": {
                    "type": "choice",
                    "choice": "C1",
                    "probabilities": {"C1": 0.9, "C2": 0.1},
                }
            },
            "usage": {"input_tokens": 50, "output_tokens": 7},
        },
        criteria={"C1", "C2", "ESCALATE"},
    )
    assert parsed["status"] == "INVALID_RESPONSE"



def test_effect_store_replays_completed_result_without_second_provider_call(
    tmp_path: Path,
) -> None:
    calls = {"n": 0}

    def producer() -> dict[str, object]:
        calls["n"] += 1
        return {"status": "DONE", "value": 7}

    first = execute_effect_once(
        effect_root=tmp_path,
        effect_id="a" * 64,
        producer=producer,
    )
    second = execute_effect_once(
        effect_root=tmp_path,
        effect_id="a" * 64,
        producer=producer,
    )

    assert first == second
    assert calls["n"] == 1


def test_effect_store_blocks_blind_retry_after_unknown_outcome(tmp_path: Path) -> None:
    effect_dir = tmp_path / ("b" * 64)
    effect_dir.mkdir(parents=True)
    (effect_dir / "STARTED.json").write_text('{"effect_id":"' + "b" * 64 + '"}\n')

    with pytest.raises(RuntimeError, match="stack_effect_outcome_unknown"):
        execute_effect_once(
            effect_root=tmp_path,
            effect_id="b" * 64,
            producer=lambda: {"should": "not run"},
        )


def test_canary_markers_are_explicit_controls_not_natural_inference() -> None:
    assert classify_shadow_stratum(title="[HYBRID_CANARY:A] dependency check", body="control") == "A"
    assert classify_shadow_stratum(title="[HYBRID_CANARY:B] ranking check", body="control") == "B"
    assert classify_shadow_stratum(title="[HYBRID_CANARY:C] coding check", body="control") == "C"
