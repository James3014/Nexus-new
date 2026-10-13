"""Offline rule snapshot guard: synthetic PASS and RED failure witnesses."""

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "scripts/ops/core_ruleset_history_audit.py"
spec = importlib.util.spec_from_file_location("core_ruleset_history_audit", MODULE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def valid():
    return {
        "id": 123,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {"type": "pull_request"},
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [
                        {"context": "Another check", "integration_id": 15368},
                        {"context": "Nexus Core issue completion", "integration_id": 15368},
                    ]
                },
            },
        ],
    }


def check(snapshot):
    return guard.evaluate(snapshot)


def test_valid():
    assert check(valid()) == []


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda s: s.update(enforcement="disabled"), "RULESET_NOT_ACTIVE"),
        (
            lambda s: s.update(bypass_actors=[{"actor_id": 5, "actor_type": "RepositoryRole"}]),
            "BYPASS_ACTORS_PRESENT",
        ),
        (lambda s: s["rules"].pop(0), "PULL_REQUEST_RULE_MISSING"),
        (
            lambda s: s["rules"][1]["parameters"]["required_status_checks"].pop(),
            "CORE_CHECK_MISSING",
        ),
        (
            lambda s: s["rules"][1]["parameters"]["required_status_checks"][-1].pop(
                "integration_id"
            ),
            "CORE_CHECK_ISSUER_UNBOUND",
        ),
        (
            lambda s: s["rules"][1]["parameters"]["required_status_checks"][-1].update(
                integration_id=999
            ),
            "CORE_CHECK_WRONG_ISSUER",
        ),
        (
            lambda s: s["conditions"]["ref_name"].update(include=["refs/heads/feature"]),
            "DEFAULT_BRANCH_NOT_INCLUDED",
        ),
    ],
)
def test_negative(change, code):
    snapshot = valid()
    change(snapshot)
    assert code in check(snapshot)


def test_input_unchanged_and_mixed_cli(tmp_path, capsys):
    a, b = valid(), valid()
    b["rules"][1]["parameters"]["required_status_checks"][-1].pop("integration_id")
    first, second = tmp_path / "good.json", tmp_path / "bad.json"
    first.write_text(json.dumps(a), encoding="utf-8")
    second.write_text(json.dumps(b), encoding="utf-8")
    before = [p.read_bytes() for p in (first, second)]
    assert guard.main([str(first), str(second)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "FAIL"
    assert [i["status"] for i in output["snapshots"]] == ["PASS", "FAIL"]
    assert [p.read_bytes() for p in (first, second)] == before


def test_single_cli_pass(tmp_path, capsys):
    path = tmp_path / "good.json"
    path.write_text(json.dumps(valid()), encoding="utf-8")
    assert guard.main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"


def test_explicit_main_is_protected():
    snapshot = valid()
    snapshot["conditions"]["ref_name"]["include"] = ["refs/heads/main"]
    assert check(snapshot) == []


def test_explicit_main_exclusion_is_rejected():
    snapshot = valid()
    snapshot["conditions"]["ref_name"]["exclude"] = ["refs/heads/main"]
    assert "DEFAULT_BRANCH_NOT_INCLUDED" in check(snapshot)


def test_default_ref_explicitly_excluded():
    snapshot = valid()
    snapshot["conditions"]["ref_name"]["exclude"] = ["~DEFAULT_BRANCH"]
    assert "DEFAULT_BRANCH_NOT_INCLUDED" in check(snapshot)


def test_malformed_included_ref_fails_closed():
    snapshot = valid()
    snapshot["conditions"]["ref_name"]["include"] = [["~DEFAULT_BRANCH"]]
    assert "DEFAULT_BRANCH_NOT_INCLUDED" in check(snapshot)


def test_missing_included_ref_fails_closed():
    snapshot = valid()
    snapshot["conditions"]["ref_name"]["include"] = None
    assert "DEFAULT_BRANCH_NOT_INCLUDED" in check(snapshot)
