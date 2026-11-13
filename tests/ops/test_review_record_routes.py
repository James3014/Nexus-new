from pathlib import Path

import pytest

from scripts.ops import review_record_check as rrc

ROOT = Path(__file__).resolve().parents[2]
HEAD = "8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe129"
OLD = "1e9f3d4ec0000000000000000000000000000000"
LOW = [{"filename": "docs/a.md"}]
HIGH = [{"filename": "scripts/ops/a.py"}]


def comment(body):
    return {"body": body, "user": {"login": "reviewer"}}


def accept(model, sha=HEAD):
    label = {"claude": "Claude", "gemini": "Gemini", "codex": "Codex", "gpt": "GPT"}[model]
    return comment(f"{label} review: ACCEPT@{sha}\n")


def evaluate(files, comments):
    return rrc.evaluate(HEAD, files, comments, [])


def test_generated_route_document_matches_table():
    assert (ROOT / "docs/ops/review_routing.md").read_text() == rrc.render_routes_markdown()


@pytest.mark.parametrize("route", rrc.REVIEW_ROUTES)
def test_each_route_accepts_its_complete_alternative(route):
    files = LOW if route.risk == "low" else HIGH
    comments = [comment(f"Claude review: ACCEPT@{OLD}\n")] if route.round == "2+" else []
    satisfied = None
    for group in route.alternatives:
        for family in group:
            if family == "claude":
                comments.append(accept("claude"))
            elif family == "cross_model":
                comments.append(accept("codex"))
            else:
                comments.append(accept(family))
        result = evaluate(files, comments)
        assert result["status"] == "OK"
        satisfied = result["satisfied_by"]
        comments = [comment(f"Claude review: ACCEPT@{OLD}\n")] if route.round == "2+" else []
    assert satisfied is not None
    assert result["route"] == ("r1" if route.round == "1" else "r2+")
    expected = (
        "claude+cross_model"
        if "cross_model" in route.alternatives[-1]
        else "gemini+codex"
        if "gemini" in route.alternatives[-1]
        else "claude"
    )
    assert satisfied == expected


@pytest.mark.parametrize("route", rrc.REVIEW_ROUTES)
def test_each_route_rejects_an_incomplete_alternative(route):
    files = LOW if route.risk == "low" else HIGH
    comments = [comment(f"Claude review: ACCEPT@{OLD}\n")] if route.round == "2+" else []
    for group in route.alternatives:
        incomplete = list(group[:-1])
        comments.extend(accept(family) for family in incomplete)
        result = evaluate(files, comments)
        assert result["status"] in {"MISSING_RECORD", "MISSING_CROSS_MODEL"}
        comments = [comment(f"Claude review: ACCEPT@{OLD}\n")] if route.round == "2+" else []


@pytest.mark.parametrize(
    ("comments", "expected"),
    [
        ([accept("gemini"), accept("codex")], "MISSING_RECORD"),
        ([comment(f"Claude review: ACCEPT@{OLD}\n"), accept("gemini")], "MISSING_RECORD"),
        (
            [
                comment(f"Claude review: ACCEPT@{OLD}\n"),
                accept("gemini"),
                accept("codex"),
                comment(f"Gemini review: REJECT@{HEAD}\n"),
            ],
            "MISSING_RECORD",
        ),
        ([comment(f"Claude review: ACCEPT@{OLD}\n"), accept("gemini"), accept("gpt")], "OK"),
        (
            [comment(f"Claude notes only {OLD}\n"), accept("gemini"), accept("codex")],
            "MISSING_RECORD",
        ),
        (
            [
                comment(f"Claude review: ACCEPT@{OLD}\n"),
                accept("gemini", OLD),
                accept("codex", OLD),
            ],
            "MISSING_RECORD",
        ),
        (
            [
                comment(f"Claude Gemini review: ACCEPT@{HEAD}\n"),
                comment(f"Claude review: ACCEPT@{OLD}\n"),
                accept("codex"),
            ],
            "MISSING_RECORD",
        ),
    ],
)
def test_route_boundary_and_withdrawal_cases(comments, expected):
    assert evaluate(LOW, comments)["status"] == expected


def test_gemini_codex_route_explains_acceptance():
    result = evaluate(
        LOW,
        [comment(f"Claude review: REJECT@{OLD}\n"), accept("gemini"), accept("codex")],
    )
    assert result["status"] == "OK"
    assert result["route"] == "r2+"
    assert result["satisfied_by"] == "gemini+codex"
    assert result["reason"] == f"round 2+ route: Gemini and Codex ACCEPT at head {HEAD[:12]}"


def test_high_risk_round_two_prefers_existing_claude_and_cross_model_route():
    result = evaluate(
        HIGH,
        [
            comment(f"Claude review: ACCEPT@{OLD}\n"),
            accept("claude"),
            accept("gemini"),
            accept("codex"),
        ],
    )
    assert result["status"] == "OK"
    assert result["satisfied_by"] == "claude+cross_model"
