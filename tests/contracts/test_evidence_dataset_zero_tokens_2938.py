"""#2938: a recorded zero token count or zero model calls stays 0, not None."""

from __future__ import annotations

import pytest

from nexus.contracts.evidence_dataset import evidence_record_from_benchmark_row

_BASE = {"task_id": "t1", "capability": "c1"}


def _counts(**fields):
    record = evidence_record_from_benchmark_row({**_BASE, **fields}, source_path="rows.jsonl")
    return record.token_counts


def test_zero_total_tokens_and_zero_model_calls_are_kept():
    counts = _counts(total_tokens=0, prompt_tokens=0, model_calls=0)
    assert counts["total"] == 0
    assert counts["model_calls"] == 0
    assert counts["prompt"] == 0


@pytest.mark.parametrize(
    ("fields", "total", "calls"),
    [
        ({"total_tokens": 0, "totaltokens": 7, "model_calls": 0, "modelcalls": 3}, 0, 0),
        ({"totaltokens": 0, "modelcalls": 0}, 0, 0),
        ({"totaltokens": 41, "modelcalls": 2}, 41, 2),
        ({"total_tokens": 1234, "model_calls": 9}, 1234, 9),
        ({}, None, None),
        ({"total_tokens": None, "totaltokens": 5, "model_calls": None, "modelcalls": 4}, 5, 4),
        ({"total_tokens": "", "totaltokens": 5, "model_calls": "", "modelcalls": 4}, 5, 4),
    ],
    ids=[
        "zero_primary_wins",
        "zero_alias",
        "alias_only",
        "nonzero",
        "missing",
        "none_falls_back",
        "empty_falls_back",
    ],
)
def test_token_and_call_counts_take_the_first_present_value(fields, total, calls):
    counts = _counts(**fields)
    assert counts["total"] == total
    assert counts["model_calls"] == calls


def test_zero_counts_survive_to_dict():
    record = evidence_record_from_benchmark_row(
        {**_BASE, "total_tokens": 0, "model_calls": 0}, source_path="rows.jsonl"
    )
    payload = record.to_dict()
    assert payload["token_counts"]["total"] == 0
    assert payload["token_counts"]["model_calls"] == 0


def test_provider_token_status_reads_the_same_model_calls_as_the_record():
    # Review of #2944: the cleanliness check still used "or", so 0 vs an alias of 3 disagreed.
    record = evidence_record_from_benchmark_row(
        {**_BASE, "model_calls": 0, "modelcalls": 3}, source_path="rows.jsonl"
    )
    assert record.token_counts["model_calls"] == 0
    assert record.provider_token_cleanliness.value == "not_applicable"
