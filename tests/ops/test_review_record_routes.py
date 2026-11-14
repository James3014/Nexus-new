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


@pytest.mark.parametrize(
    "codex_comment",
    [
        (
            "## Codex adversarial review\n"
            f"Round 3 REJECT at {HEAD}; rebutted, not fixed: cap reached.\n"
        ),
        (
            "## Codex adversarial review\n"
            f"Head {HEAD}\nRound 3 REJECT; rebutted, not fixed: cap reached.\n"
        ),
    ],
)
def test_gemini_accept_plus_codex_rebuttal_does_not_satisfy_round_two(codex_comment):
    result = evaluate(
        LOW,
        [comment(f"Claude review: ACCEPT@{OLD}\n"), accept("gemini"), comment(codex_comment)],
    )
    assert result["route"] == "r2+"
    assert result["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "quoted_old_record",
    [
        f"> ## Review record -- head {OLD}\n> Claude verdict: ACCEPT\n",
        f"```\n## Review record -- head {OLD}\nClaude verdict: ACCEPT\n```\n",
    ],
)
def test_quoted_or_fenced_old_claude_record_does_not_start_round_two(quoted_old_record):
    result = evaluate(LOW, [comment(quoted_old_record), accept("gemini"), accept("codex")])
    assert result["route"] == "r1"
    assert result["status"] == "MISSING_RECORD"


def test_real_old_claude_record_header_starts_round_two():
    result = evaluate(
        LOW,
        [
            comment(f"## Review record -- head {OLD}\nClaude verdict: ACCEPT@{OLD}\n"),
            accept("gemini"),
            accept("codex"),
        ],
    )
    assert result["route"] == "r2+"
    assert result["status"] == "OK"


@pytest.mark.parametrize(
    "quoted_reject",
    [
        f"> Claude review: REJECT@{OLD}",
        f"```\nClaude review: REJECT@{OLD}\n```",
        f"| Claude | REJECT@{OLD} |",
        f"intro\n\n    Claude review: REJECT@{OLD}",
        f"`Claude review: REJECT@{OLD}`",
        (
            f"> ## Review record — head `{OLD}`\n"
            f"> **Independent Claude review** (Claude Opus 5.5, separate agent): "
            f"**REJECT at {OLD}**."
        ),
        f"Claude summary follows. Gemini review: REJECT@{OLD}",
    ],
)
def test_quoted_old_claude_reject_does_not_start_round_two(quoted_reject):
    result = evaluate(LOW, [comment(quoted_reject), accept("gemini"), accept("codex")])
    assert result["route"] == "r1"
    assert result["status"] == "MISSING_RECORD"


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


def test_short_sha_of_current_head_does_not_start_round_two():
    # A Claude REJECT written with a short prefix of the current head is round 1:
    # Gemini + Codex ACCEPT must not replace it (Gemini round-2 finding).
    head = "8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe129"
    files = [{"filename": "docs/a.md"}]
    comments = [
        {"body": f"Claude review: REJECT@{head[:12]}\n", "user": {"login": "reviewer"}},
        {"body": f"Gemini review: ACCEPT@{head}\n", "user": {"login": "reviewer"}},
        {"body": f"Codex review: ACCEPT@{head}\n", "user": {"login": "reviewer"}},
    ]
    result = rrc.evaluate(head, files, comments, [])
    assert result["route"] == "r1"
    assert result["status"] != "OK"


def _review_record(head, verdict):
    return comment(
        f"## Review record — head `{head}`\n"
        f"**Independent Claude review** (Claude Opus 5.5, separate agent): "
        f"**{verdict} at {head}**.\n"
    )


def _cross_model_record(model, verdict):
    return comment(f"**Cross-model review ({model})**\n- Verdict: **{verdict}** at {HEAD}\n")


@pytest.mark.parametrize(
    ("files", "bodies", "expected"),
    [
        (
            LOW,
            [
                f"Claude review: REJECT@{OLD}",
                f"Claude review: REJECT@{HEAD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            HIGH,
            [
                f"Claude review: REJECT@{OLD}",
                f"Claude review: REJECT@{HEAD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
                f"Claude review: REJECT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Claude review: ACCEPT@{HEAD}",
                f"Claude review: REJECT@{HEAD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            HIGH,
            [
                _review_record(OLD, "REJECT").get("body"),
                _review_record(HEAD, "REJECT").get("body"),
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Claude review: REJECT@{HEAD[:9]}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Claude review: REJECT@{HEAD[:7]}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
                f"Cross-model review: REJECT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
                _cross_model_record("Gemini 3.8 Flash via agy", "REJECT")["body"],
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
                _cross_model_record("GPT-6 Luna via codex", "REJECT")["body"],
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
                _cross_model_record("Gemini cross-model review", "REJECT")["body"],
            ],
            "MISSING_RECORD",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
                f"OpenAI review: REJECT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
        (
            HIGH,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Claude review: ACCEPT@{HEAD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
                _cross_model_record("Gemini 3.8 Flash via agy", "REJECT")["body"],
            ],
            "MISSING_CROSS_MODEL",
        ),
        (
            LOW,
            [
                f"Gemini review: REJECT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "MISSING_RECORD",
        ),
    ],
)
def test_must_block_review_record_routes(files, bodies, expected):
    assert evaluate(files, [comment(body) for body in bodies])["status"] == expected


@pytest.mark.parametrize(
    ("files", "bodies", "expected_route", "satisfied_by"),
    [
        (
            LOW,
            [
                f"Claude review: REJECT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "r2+",
            "gemini+codex",
        ),
        (
            LOW,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"GPT review: ACCEPT@{HEAD}",
            ],
            "r2+",
            "gemini+codex",
        ),
        (
            LOW,
            [
                f"Claude review: REJECT@{OLD}",
                f"Claude review: REJECT@{HEAD}",
                f"Claude review: ACCEPT@{HEAD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "r2+",
            "claude",
        ),
        (
            HIGH,
            [
                f"Claude review: ACCEPT@{OLD}",
                f"Claude review: ACCEPT@{HEAD}",
                f"Gemini review: ACCEPT@{HEAD}",
                f"Codex review: ACCEPT@{HEAD}",
            ],
            "r2+",
            "claude+cross_model",
        ),
    ],
)
def test_must_pass_review_record_routes(files, bodies, expected_route, satisfied_by):
    result = evaluate(files, [comment(body) for body in bodies])
    assert result["status"] == "OK"
    assert result["route"] == expected_route
    assert result["satisfied_by"] == satisfied_by


def test_older_gemini_reject_does_not_start_round_two():
    result = evaluate(
        LOW,
        [comment(f"Gemini review: REJECT@{OLD}"), accept("gemini"), accept("codex")],
    )
    assert result["route"] == "r1"
    assert result["status"] == "MISSING_RECORD"


@pytest.mark.parametrize(
    "line_factory",
    [
        lambda comment_index, line_index: (
            f"> Claude review: ACCEPT@{comment_index:02x}{line_index:038x}"
        ),
        lambda comment_index, line_index: (
            f"Claude review record head note {comment_index:02x}{line_index:038x}"
        ),
        lambda comment_index, line_index: (
            f"finding {line_index} {comment_index:02x}{line_index:038x}"
        ),
    ],
)
def test_older_sha_scan_is_linear_enough(line_factory):
    # Candidate SHA work is capped at 64 distinct tokens per comment.
    comments = [
        comment("\n".join(line_factory(comment_index, line_index) for line_index in range(400)))
        for comment_index in range(3)
    ]
    import time

    started = time.perf_counter()
    rrc.evaluate(HEAD, LOW[0:0] + LOW, comments, [])
    assert time.perf_counter() - started < 1


@pytest.mark.parametrize("rejecter", ["Cross-model review", "OpenAI review"])
def test_unnamed_reject_withdraws_both_route_families(rejecter):
    # Gemini ACCEPT, then a REJECT naming neither family, then a Codex ACCEPT: the Codex
    # ACCEPT answers only its own family, so the Gemini ACCEPT must not be left standing.
    head = "8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe129"
    older = "1234567abcdef1234567abcdef1234567abcdef0"
    comments = [
        {"body": f"Claude review: ACCEPT@{older}\n", "user": {"login": "u"}},
        {"body": f"Gemini review: ACCEPT@{head}\n", "user": {"login": "u"}},
        {"body": f"{rejecter}: REJECT@{head}\n", "user": {"login": "u"}},
        {"body": f"Codex review: ACCEPT@{head}\n", "user": {"login": "u"}},
    ]
    result = rrc.evaluate(head, [{"filename": "docs/a.md"}], comments, [])
    assert result["status"] != "OK"
