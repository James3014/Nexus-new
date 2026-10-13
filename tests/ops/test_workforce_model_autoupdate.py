"""Offline tests for the #1996 automatic Workforce model-version updater.

No provider, git or GitHub effect: every command goes through a fake runner, the attestation
call is a fake, and the yaml validator is the real (installed) ``WorkforcePolicyLoader``.
"""

from __future__ import annotations

import ast
import json
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ops import workforce_model_autoupdate as wf
from tests.ops.workforce_autoupdate_fixtures import (
    AGY_MODELS_1_3_4,
    MODEL_WORKFORCE_RUNTIME_2766C15,
)

# Some stages take file paths; materialize the Python fixtures once per session.
_FIXTURE_DIR = Path(tempfile.mkdtemp(prefix="workforce-autoupdate-fixtures-"))
CATALOG_FIXTURE = _FIXTURE_DIR / "agy_models_1.3.4.stdout"
CATALOG_FIXTURE.write_text(AGY_MODELS_1_3_4, encoding="utf-8")
YAML_FIXTURE = _FIXTURE_DIR / "model_workforce_runtime_2766c15.yaml"
YAML_FIXTURE.write_text(MODEL_WORKFORCE_RUNTIME_2766C15, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = "2026-10-13"
HEAD = "a" * 40
MERGE_SHA = "b" * 40


def _catalog(*ids: str) -> wf.Catalog:
    return wf.parse_catalog("".join(f"{i}\t{wf.expected_label(i)}\n" for i in ids))


def _policy(text: str | None = None) -> dict[str, Any]:
    return yaml.safe_load(text if text is not None else MODEL_WORKFORCE_RUNTIME_2766C15)


def _validator(text: str) -> str:
    return wf.validate_with_runtime(text)  # installed (pinned) nexus_runtime validator


# ---------------------------------------------------------------- discover


def test_discovery_parses_real_agy_1_3_4_fixture() -> None:
    raw = AGY_MODELS_1_3_4
    assert len(raw.splitlines()) == 6
    catalog = wf.parse_catalog(raw)
    assert catalog.ok
    assert [e.model_id for e in catalog.entries] == [
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-medium",
        "gemini-3.8-flash-low",
    ]
    medium = catalog.entries[1]
    assert (medium.family, medium.tier, medium.version, medium.label) == (
        "gemini-flash",
        "medium",
        (3, 8),
        "Gemini 3.8 Flash (Medium)",
    )
    assert [line.split("\t")[0] for line in catalog.unrecognized] == [
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking",
        "gpt-oss-120b-medium",
    ]


def test_catalog_fixture_contains_no_secrets() -> None:
    raw = AGY_MODELS_1_3_4
    assert not re.search(r"(?i)(token|secret|password|api[_-]?key|bearer|@|sk-|ya29\.)", raw)
    assert all(re.fullmatch(r"[a-z0-9.\-]+\t[A-Za-z0-9.() \-]+", line) for line in raw.splitlines())


def test_discover_runs_agy_models_and_fails_closed_on_rc() -> None:
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], **_: Any) -> wf.CmdResult:
        calls.append(list(argv))
        if argv[1] == "models":
            return wf.CmdResult(0, AGY_MODELS_1_3_4, "Fetching available models...\n")
        return wf.CmdResult(0, "1.3.4\n")

    catalog = wf.discover(agy_bin="agy", runner=runner)
    assert catalog.ok and catalog.agy_version == "1.3.4"
    assert calls == [["agy", "models"], ["agy", "--version"]]
    failed = wf.discover(runner=lambda argv, **_: wf.CmdResult(1, "", "boom"))
    assert not failed.ok and failed.error == "AGY_MODELS_RC_1"
    assert wf.decide(_policy(), failed).kind == wf.BLOCKED


# ---------------------------------------------------------------- decide


def test_decide_noop_when_default_served_and_nothing_newer() -> None:
    decision = wf.decide(_policy(), _catalog("gemini-3.7-flash-medium", "gemini-3.6-flash-high"))
    assert decision.kind == wf.NOOP


def test_decide_newer_version_same_tier_reuses_registered_worker() -> None:
    decision = wf.decide(_policy(), _catalog("gemini-3.7-flash-medium", "gemini-3.8-flash-medium"))
    assert decision.kind == wf.SWITCH
    assert (decision.old_worker, decision.new_worker) == ("agy_flash_37_medium", "agy_flash_38")
    assert decision.roles == ("fast_bounded_implementation",)
    assert not decision.predecessor_retired and not decision.register_new_worker
    # superseded (still served): the campaign pin keeps its exact identity
    assert decision.untouched_pins == (
        "campaign_routing.CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01.fast_bounded_implementation",
    )
    assert decision.flipped_pins == ()


def test_decide_default_retired_switches_to_served_successor() -> None:
    decision = wf.decide(_policy(), wf.parse_catalog(AGY_MODELS_1_3_4))
    assert decision.kind == wf.SWITCH
    assert decision.old_model == "gemini-3.7-flash-medium"
    assert decision.new_model == "gemini-3.8-flash-medium"
    assert decision.predecessor_retired
    assert decision.flipped_pins and not decision.untouched_pins


def test_decide_newest_version_registers_new_worker() -> None:
    decision = wf.decide(_policy(), _catalog("gemini-3.8-flash-medium", "gemini-3.9-flash-medium"))
    assert decision.kind == wf.SWITCH
    assert decision.new_model == "gemini-3.9-flash-medium"
    assert decision.new_worker == "agy_flash_39" and decision.register_new_worker


def test_decide_unknown_formats_are_recorded_but_ignored() -> None:
    raw = (
        "gemini-3.7-flash-medium\tGemini 3.7 Flash (Medium)\n"
        "gemini-4.0-flash-ultra\tGemini 4.0 Flash (Ultra)\n"
        "gemini-3.9-flash-medium\tGemini 3.9 Flash Preview\n"  # label does not match id
        "garbage line without tab\n"
    )
    catalog = wf.parse_catalog(raw)
    assert [e.model_id for e in catalog.entries] == ["gemini-3.7-flash-medium"]
    assert len(catalog.unrecognized) == 3
    decision = wf.decide(_policy(), catalog)
    assert decision.kind == wf.NOOP
    assert sum(note.startswith("unrecognized_catalog_line:") for note in decision.notes) == 3


def test_decide_refuses_cross_tier_and_cross_family() -> None:
    # 3.7 medium retired; only other tiers / families are served -> blocked, never crossed.
    catalog = _catalog("gemini-3.9-flash-high", "gemini-3.8-flash-low")
    decision = wf.decide(_policy(), catalog)
    assert decision.kind == wf.BLOCKED
    assert decision.reason.startswith("DEFAULT_RETIRED_NO_SAME_TIER_SUCCESSOR")
    assert decision.new_model == ""


def test_decide_never_raises_autonomy() -> None:
    text = MODEL_WORKFORCE_RUNTIME_2766C15
    block = re.search(r"\n  agy_flash_38:\n(?:    .*\n|      .*\n)+", text)
    assert block
    raised = text.replace(
        block.group(0), block.group(0).replace("    autonomy: L3\n", "    autonomy: L4\n")
    )
    decision = wf.decide(_policy(raised), _catalog("gemini-3.8-flash-medium"))
    assert decision.kind == wf.BLOCKED and decision.reason == "AUTONOMY_WOULD_RAISE:agy_flash_38"

    # a newly registered worker copies the predecessor autonomy exactly
    decision = wf.decide(_policy(), _catalog("gemini-3.9-flash-medium"))
    rendered = wf.render_change(
        MODEL_WORKFORCE_RUNTIME_2766C15, decision, today=TODAY, validator=lambda _t: ""
    )
    workers = yaml.safe_load(rendered.text)["workers"]
    assert workers["agy_flash_39"]["autonomy"] == workers["agy_flash_37_medium"]["autonomy"]


# ---------------------------------------------------------------- render + real validator


def test_render_retired_switch_passes_real_validator() -> None:
    text = MODEL_WORKFORCE_RUNTIME_2766C15
    decision = wf.decide(_policy(), wf.parse_catalog(AGY_MODELS_1_3_4))
    result = wf.render_change(
        text, decision, today=TODAY, agy_version="1.3.4", validator=_validator
    )
    assert result.ok, (result.reason, result.validator)
    data = yaml.safe_load(result.text)
    online = data["routing"]["online"]
    assert online["fast_bounded_implementation"] == "agy_flash_38"
    assert online["route_defaults"]["fast_bounded_implementation"]["current_default"] == (
        "agy_flash_38"
    )
    assert online["fast_bounded_implementation_fallback"] == "agy_flash"  # fallback untouched
    old = data["workers"]["agy_flash_37_medium"]
    assert old["availability"] == "UNAVAILABLE" and old["default_route"] is False
    assert data["workers"]["agy_flash_38"]["default_route"] is True
    assert data["last_verified"] == TODAY
    # nothing outside the Workforce change moved
    before = _policy()
    for key in ("states", "provider_policy", "benchmark_snapshot", "context_policy"):
        assert data[key] == before[key]


def test_render_new_worker_passes_real_validator_without_inherited_evidence() -> None:
    text = MODEL_WORKFORCE_RUNTIME_2766C15
    decision = wf.decide(_policy(), _catalog("gemini-3.9-flash-medium", "gemini-3.6-flash-high"))
    result = wf.render_change(text, decision, today=TODAY, validator=_validator)
    assert result.ok, (result.reason, result.validator)
    new = yaml.safe_load(result.text)["workers"]["agy_flash_39"]
    assert new["model"] == "gemini-3.9-flash-medium"
    assert new["state"] == "REGISTERED_CONDITIONAL" and new["availability"] == "AVAILABLE"
    assert "calibration_evidence" not in new and "Autonomy is inherited" in new["model_id_note"]


def test_render_negative_case_real_validator_rejects() -> None:
    # The fallback already points at the successor: default == fallback is invalid.
    text = (
        YAML_FIXTURE
        .read_text()
        .replace(
            "    fast_bounded_implementation_fallback: agy_flash\n",
            "    fast_bounded_implementation_fallback: agy_flash_38\n",
        )
        .replace("        fallback: agy_flash\n", "        fallback: agy_flash_38\n")
    )
    assert wf.validate_with_runtime(text) == ""  # still valid before the switch
    decision = wf.decide(_policy(text), _catalog("gemini-3.8-flash-medium"))
    result = wf.render_change(text, decision, today=TODAY, validator=_validator)
    assert not result.ok and result.reason == "VALIDATOR_REJECTED"
    assert "identical default and fallback" in result.validator


# ---------------------------------------------------------------- fakes


class FakeGh:
    """Fake runner for gh/git/claude commands; records every argv."""

    def __init__(self, *, head: str = HEAD, checks: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.heads = [head]
        self.checks = checks if checks is not None else [{"name": "ci", "bucket": "pass"}]
        self.merged = False
        self.hook_stdout = "GO\n"
        self.open_prs: list[dict[str, Any]] = []
        self.inputs: list[str] = []

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> wf.CmdResult:
        args = list(argv)
        self.calls.append(args)
        if kwargs.get("input_text"):
            self.inputs.append(str(kwargs["input_text"]))
        if args[0] == "gh" and args[1:3] == ["pr", "view"]:
            head = self.heads.pop(0) if len(self.heads) > 1 else self.heads[0]
            return wf.CmdResult(
                0,
                json.dumps({
                    "number": int(args[3]),
                    "state": "MERGED" if self.merged else "OPEN",
                    "headRefOid": head,
                    "mergeCommit": {"oid": MERGE_SHA} if self.merged else None,
                }),
            )
        if args[0] == "gh" and args[1:3] == ["pr", "checks"]:
            return wf.CmdResult(0, json.dumps(self.checks))
        if args[0] == "gh" and args[1:3] == ["pr", "list"]:
            return wf.CmdResult(0, json.dumps(self.open_prs))
        if args[0] == "gh" and args[1:3] == ["pr", "diff"]:
            return wf.CmdResult(0, "diff --git a/x b/x\n")
        if args[0] == "gh" and args[1:3] == ["pr", "merge"]:
            self.merged = True
            return wf.CmdResult(0, "")
        if args[0] == "gh" and args[2] == "comment":
            return wf.CmdResult(0, "")
        if args[0] == "hook":
            return wf.CmdResult(0, self.hook_stdout)
        raise AssertionError(f"unexpected command: {args}")

    def ran(self, *prefix: str) -> bool:
        return any(call[: len(prefix)] == list(prefix) for call in self.calls)


DECISION = wf.Decision(
    wf.SWITCH,
    roles=("fast_bounded_implementation",),
    old_worker="agy_flash_37_medium",
    old_model="gemini-3.7-flash-medium",
    new_model="gemini-3.8-flash-medium",
    new_label="Gemini 3.8 Flash (Medium)",
    new_worker="agy_flash_38",
)


def _accept(head: str = HEAD) -> wf.ReviewResult:
    return wf.ReviewResult(wf.ACCEPT, ("in scope",), head, recorded=True)


# ---------------------------------------------------------------- review / merge gates


def test_reviewer_reject_blocks_merge() -> None:
    fake = FakeGh()
    gh = wf.GitHub(runner=fake)
    result = wf.review(
        gh,
        lambda _p: (wf.REJECT, ("touches fallback",)),
        repo=wf.RUNTIME_REPO,
        pr=7,
        head=HEAD,
        kind="runtime",
        decision=DECISION,
    )
    assert result.verdict == wf.REJECT and result.recorded
    assert fake.ran("gh", "pr", "comment", "7")
    merged = wf.merge(gh, repo=wf.RUNTIME_REPO, pr=7, head=HEAD, review_result=result)
    assert not merged.ok and merged.reason == "REVIEW_NOT_ACCEPT"
    assert not fake.ran("gh", "pr", "merge")


def test_reviewer_failure_or_bad_output_is_reject() -> None:
    def broken(_prompt: str) -> tuple[str, tuple[str, ...]]:
        raise OSError("claude missing")

    fake = FakeGh()
    result = wf.review(
        wf.GitHub(runner=fake),
        broken,
        repo=wf.RUNTIME_REPO,
        pr=7,
        head=HEAD,
        kind="runtime",
        decision=DECISION,
    )
    assert result.verdict == wf.REJECT
    assert wf.parse_review_output("not json")[0] == wf.REJECT
    assert wf.parse_review_output(json.dumps({"result": '{"verdict": "MAYBE", "reasons": []}'}))[
        0
    ] == (wf.REJECT)
    ok = json.dumps({"structured_output": {"verdict": "ACCEPT", "reasons": ["ok"]}})
    assert wf.parse_review_output(ok) == (wf.ACCEPT, ("ok",))
    unavailable = wf.Reviewer(runner=lambda *_a, **_k: wf.CmdResult(127, "", "missing"))
    assert unavailable("prompt")[0] == wf.REJECT


def test_reviewer_argv_is_pinned_and_read_only() -> None:
    argv = wf.Reviewer(claude_bin="claude").argv()
    assert argv[:2] == ["claude", "-p"]
    assert argv[argv.index("--model") + 1] == wf.DEFAULT_REVIEWER_MODEL
    # B2: no tools at all, no MCP servers, no settings/hooks/plugins
    assert argv[argv.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in argv and "--mcp-config" not in argv
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert "Bash" in argv[argv.index("--disallowedTools") + 1]
    assert "bypassPermissions" not in argv and "--dangerously-skip-permissions" not in argv


def test_red_checks_block_merge() -> None:
    fake = FakeGh(checks=[{"name": "ci", "bucket": "pass"}, {"name": "core", "bucket": "fail"}])
    merged = wf.merge(
        wf.GitHub(runner=fake), repo=wf.NEXUS_REPO, pr=9, head=HEAD, review_result=_accept()
    )
    assert not merged.ok and merged.reason == "CHECKS_RED:core"
    assert not fake.ran("gh", "pr", "merge")
    pending = FakeGh(checks=[{"name": "ci", "bucket": "pending"}])
    merged = wf.merge(
        wf.GitHub(runner=pending), repo=wf.NEXUS_REPO, pr=9, head=HEAD, review_result=_accept()
    )
    assert merged.reason == "CHECKS_PENDING"
    none = FakeGh(checks=[])
    merged = wf.merge(
        wf.GitHub(runner=none), repo=wf.NEXUS_REPO, pr=9, head=HEAD, review_result=_accept()
    )
    assert merged.reason == "CHECKS_NO_REQUIRED_CHECKS"


def test_head_drift_blocks_merge_and_review() -> None:
    fake = FakeGh(head="c" * 40)
    merged = wf.merge(
        wf.GitHub(runner=fake), repo=wf.NEXUS_REPO, pr=9, head=HEAD, review_result=_accept()
    )
    assert not merged.ok and merged.reason == "CHECKS_HEAD_DRIFT"
    stale_review = wf.merge(
        wf.GitHub(runner=FakeGh()),
        repo=wf.NEXUS_REPO,
        pr=9,
        head=HEAD,
        review_result=_accept("d" * 40),
    )
    assert stale_review.reason == "REVIEW_HEAD_MISMATCH"
    drifting = FakeGh()
    drifting.heads = [HEAD, "e" * 40]  # head moves between the two reads around the diff
    result = wf.review(
        wf.GitHub(runner=drifting),
        lambda _p: (wf.ACCEPT, ()),
        repo=wf.NEXUS_REPO,
        pr=9,
        head=HEAD,
        kind="pin",
        decision=DECISION,
    )
    assert result.verdict == wf.REJECT and result.reasons == ("head_drift_during_review",)


def test_green_accept_merges_with_head_cas_and_hook() -> None:
    fake = FakeGh()
    merged = wf.merge(
        wf.GitHub(runner=fake),
        repo=wf.RUNTIME_REPO,
        pr=7,
        head=HEAD,
        review_result=_accept(),
        pre_merge_hook="hook --queue",
    )
    assert merged.ok and merged.merge_sha == MERGE_SHA
    merge_call = next(c for c in fake.calls if c[1:3] == ["pr", "merge"])
    assert merge_call[-2:] == ["--match-head-commit", HEAD] and "--merge" in merge_call
    assert ["hook", "--queue", wf.RUNTIME_REPO, "7", HEAD] in fake.calls

    blocked = FakeGh()
    blocked.hook_stdout = "WAIT\n"
    result = wf.merge(
        wf.GitHub(runner=blocked),
        repo=wf.RUNTIME_REPO,
        pr=7,
        head=HEAD,
        review_result=_accept(),
        pre_merge_hook="hook",
    )
    assert not result.ok and result.reason.startswith("PRE_MERGE_HOOK")
    assert not blocked.ran("gh", "pr", "merge")


# ---------------------------------------------------------------- attestation


def _identity_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "requested_model": "gemini-3.8-flash-medium",
        "observed_model": "gemini-3.8-flash-medium",
        "observed_model_label": "Gemini 3.8 Flash (Medium)",
        "model_identity_status": "MODEL_IDENTITY_OK",
        "provider_call_attempted": True,
        "account_alias_hash": "h1",
        "agy_no_tools_prefix_applied": True,
        "response": "should not be copied",
    }
    payload.update(overrides)
    return payload


def test_attestation_requires_exact_id_and_label() -> None:
    ok = wf.attest(
        "gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)", call=lambda _m: _identity_payload()
    )
    assert ok.ok and "response" not in ok.receipt
    mismatch = wf.attest(
        "gemini-3.8-flash-medium",
        "Gemini 3.8 Flash (Medium)",
        call=lambda _m: _identity_payload(observed_model_label="Gemini 3.8 Flash (High)"),
    )
    assert not mismatch.ok and mismatch.reason == "IDENTITY_MISMATCH"
    unobserved = wf.attest(
        "gemini-3.8-flash-medium",
        "Gemini 3.8 Flash (Medium)",
        call=lambda _m: _identity_payload(model_identity_status="MODEL_IDENTITY_UNOBSERVED"),
    )
    assert not unobserved.ok


def _cfg(tmp_path: Path, **overrides: Any) -> wf.Config:
    values: dict[str, Any] = {
        "runtime_repo": tmp_path / "runtime",
        "nexus_repo": tmp_path / "nexus",
        "yaml_path": YAML_FIXTURE,
        "catalog_file": CATALOG_FIXTURE,
        "state_dir": tmp_path / "state",
        "today": TODAY,
    }
    values.update(overrides)
    return wf.Config(**values)


def test_attestation_mismatch_blocks_run_before_any_pr(tmp_path: Path) -> None:
    fake = FakeGh()
    deps = wf.Deps(
        runner=fake,
        attest_call=lambda _m: _identity_payload(observed_model="gemini-3.8-flash-high"),
        validator=lambda _t: "",
    )
    result = wf.run(_cfg(tmp_path), deps)
    assert result.outcome == wf.BLOCKED
    assert result.reason == "ATTESTATION:IDENTITY_MISMATCH"
    # only the #1996 notification comment; no git, no PR
    assert [c[:3] for c in fake.calls] == [["gh", "issue", "comment"]]
    receipt = json.loads(Path(result.receipt_path).read_text())
    assert receipt["attestation"]["ok"] is False and receipt["outcome"] == wf.BLOCKED


# ---------------------------------------------------------------- run: dry-run, idempotency, lock


def _no_effects(argv: Sequence[str], **_: Any) -> wf.CmdResult:
    raise AssertionError(f"dry-run must not run commands: {list(argv)}")


def test_dry_run_prints_plan_without_effects(tmp_path: Path, capsys: Any) -> None:
    def no_attest(_model: str) -> dict[str, Any]:
        raise AssertionError("dry-run must not attest")

    deps = wf.Deps(runner=_no_effects, attest_call=no_attest, validator=_validator)
    result = wf.run(_cfg(tmp_path, dry_run=True), deps)
    assert result.outcome == "DRY_RUN"
    actions = [(step.repo, step.action) for step in result.plan]
    assert actions[0] == ("local", "attest")
    assert (wf.RUNTIME_REPO, "merge") in actions
    assert actions.index((wf.RUNTIME_REPO, "merge")) < actions.index((wf.NEXUS_REPO, "pr"))
    receipt = json.loads(Path(result.receipt_path).read_text())
    assert receipt["render"]["validator"] == "OK"
    assert "+    default_route: true" in receipt["rendered_diff"]
    assert not (tmp_path / "state" / "state.json").exists()


def test_cli_dry_run_output(tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(wf, "validate_with_runtime", lambda text, runtime_src=None: "")
    code = wf.main([
        "--runtime-repo",
        str(tmp_path),
        "--yaml",
        str(YAML_FIXTURE),
        "--catalog-file",
        str(CATALOG_FIXTURE),
        "--state-dir",
        str(tmp_path / "state"),
        "--dry-run",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "outcome: DRY_RUN" in out
    assert "agy_flash_37_medium (gemini-3.7-flash-medium) -> agy_flash_38" in out
    assert "plan  1. [local] attest" in out


def test_idempotent_noop_and_open_pr_reuse(tmp_path: Path) -> None:
    noop_catalog = tmp_path / "noop.stdout"
    noop_catalog.write_text("gemini-3.7-flash-medium\tGemini 3.7 Flash (Medium)\n")
    cfg = _cfg(tmp_path, catalog_file=noop_catalog)
    deps = wf.Deps(runner=_no_effects, validator=lambda _t: "")
    assert wf.run(cfg, deps).outcome == wf.NOOP
    second = wf.run(cfg, deps)
    assert second.outcome == "SKIPPED_IDEMPOTENT"
    assert len(list((tmp_path / "state" / "runs").glob("*.json"))) == 2

    key_a = wf.idempotency_key(wf.parse_catalog(noop_catalog.read_text()), b"yaml")
    assert key_a == wf.idempotency_key(wf.parse_catalog(noop_catalog.read_text()), b"yaml")
    assert key_a != wf.idempotency_key(wf.parse_catalog(noop_catalog.read_text()), b"yaml2")


def test_lock_contention_returns_locked(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    with wf.file_lock(cfg.state_dir / "autoupdate.lock"):
        result = wf.run(cfg, wf.Deps(runner=_no_effects))
    assert result.outcome == "LOCKED"
    assert json.loads(Path(result.receipt_path).read_text())["outcome"] == "LOCKED"


# ---------------------------------------------------------------- Nexus-new pin + anchor rendering


OLD_PIN = re.search(
    r"nexus-runtime\.git@([0-9a-f]{40})", (REPO_ROOT / "pyproject.toml").read_text()
).group(1)  # type: ignore[union-attr]
NEW_PIN = "f" * 40


def test_render_pin_files_rebinds_pin_and_lock_digests() -> None:
    mirror = b"schema: nexus.model_workforce.v1\n"
    result = wf.render_pin_files(REPO_ROOT, old_sha=OLD_PIN, new_sha=NEW_PIN, mirror_yaml=mirror)
    assert result.ok, result.reason
    assert set(result.files) == set(wf.SCOPE_FILES["pin"])
    for rel in wf.PIN_FILES:
        text = result.files[rel].decode()
        assert OLD_PIN not in text and NEW_PIN in text
    new_lock = wf._sha256(result.files["uv.lock"])
    for rel in wf.LOCK_DIGEST_FILES:
        assert new_lock in result.files[rel].decode()
    assert result.files[wf.MIRROR_YAML_PATH] == mirror
    assert not wf.render_pin_files(
        REPO_ROOT, old_sha="0" * 40, new_sha=NEW_PIN, mirror_yaml=mirror
    ).ok


def test_render_anchor_files_adds_exact_transition() -> None:
    transition = ("1" * 64, "2" * 64, "3" * 64, "4" * 64)
    result = wf.render_anchor_files(
        REPO_ROOT,
        old_sha=OLD_PIN,
        new_sha=NEW_PIN,
        pin_pr=2001,
        pin_issue=2000,
        transition=transition,
    )
    assert result.ok, result.reason
    anchor = result.files[wf.ANCHOR_FILE].decode()
    tests = result.files[wf.ANCHOR_TEST_FILE].decode()
    ast.parse(anchor)
    ast.parse(tests)
    assert anchor.count("TRUSTED_PR2001_DEPENDENCY_SNAPSHOT_TRANSITION") == 2
    assert f'"{NEW_PIN}"' in anchor and f'"{OLD_PIN}"' not in anchor
    assert "def test_pr2001_dependency_snapshot_transition_allows_only_exact_binding" in tests
    namespace: dict[str, Any] = {}
    record = re.search(
        r"TRUSTED_PR2001_DEPENDENCY_SNAPSHOT_TRANSITION: .*? = (\(.*?\n\))\n", anchor, re.S
    )
    assert record
    exec(f"value = {record.group(1)}", namespace)  # noqa: S102 - literal tuple from our render
    assert namespace["value"] == (2001, transition)


def test_pr_bodies_carry_issue_markers() -> None:
    body = wf.nexus_pr_body("pin", DECISION, 2000, NEW_PIN)
    assert "<!-- NEXUS_CORE_ISSUE: 2000 -->" in body
    intent = re.search(r"NEXUS_ISSUE_INTENT_V1\n(.*?)\nNEXUS_ISSUE_INTENT_V1", body, re.S)
    assert intent and json.loads(intent.group(1)) == [{"issue": 2000, "on_merge": "KEEP_OPEN"}]
    lane = re.search(r"NEXUS_MERGE_LANE_V1\n(.*?)\nNEXUS_MERGE_LANE_V1", body, re.S)
    assert lane
    assert json.loads(lane.group(1))["binding_hash"] == (
        "4574e58d3e14f275ecf68806e2a4312339d23479e3841e18fd6d2e096218e0f7"
    )
    assert "Closes" not in body
    attestation = wf.Attestation(True, DECISION.new_model, DECISION.new_label, receipt={"a": 1})
    runtime = wf.runtime_pr_body(DECISION, attestation, 55)
    assert "<!-- NEXUS_CORE_ISSUE: 55 -->" in runtime and "Closes" not in runtime


def test_notify_mentions_gateway_pending(tmp_path: Path) -> None:
    fake = FakeGh()
    assert wf.notify(
        wf.GitHub(runner=fake),
        decision=DECISION,
        outcome="MERGED",
        receipt={"merges": {"runtime": MERGE_SHA}, "idempotency_key": "k"},
    )
    call = next(c for c in fake.calls if c[1:3] == ["issue", "comment"])
    assert call[3] == "1996" and call[5] == wf.NEXUS_REPO
    body = fake.inputs[-1]
    assert "Gateway reload is pending Owner #526 activation" in body
    assert MERGE_SHA in body and "agy_flash_37_medium" in body


# ---------------------------------------------------------------- full live flow (all fakes)


class FakeWorld:
    """Stateful git + gh + nexus-certify fake: remote branches, commits, PRs and main per repo."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.calls: list[list[str]] = []
        self.main = {"runtime": "1" * 40, "nexus": "2" * 40}
        self.commits: dict[str, dict[str, str]] = {}
        self.branches: dict[tuple[str, str], str] = {}
        self.prs: dict[int, dict[str, Any]] = {}
        self.issues: list[dict[str, Any]] = []
        self.wt_repo: dict[str, str] = {}
        self.wt_head: dict[str, str] = {}
        self.wt_files: dict[str, list[str]] = {}
        self.red_prs: set[int] = set()
        self.comments: list[str] = []
        self.counter = 0
        self.next_pr = 100

    def _new_sha(self) -> str:
        self.counter += 1
        return f"{self.counter:040x}"

    @staticmethod
    def _repo_of_path(path: Path) -> str:
        return "runtime" if path.name == "runtime-clone" else "nexus"

    @staticmethod
    def _repo_of_slug(slug: str) -> str:
        return "runtime" if slug == wf.RUNTIME_REPO else "nexus"

    def content(self, repo: str, sha: str, rel: str) -> str:
        if rel in self.commits.get(sha, {}):
            return self.commits[sha][rel]
        if repo == "runtime":
            return YAML_FIXTURE.read_text()
        return (REPO_ROOT / rel).read_text()

    def head_of(self, pr: dict[str, Any]) -> str:
        return pr["frozen_head"] if pr["merged"] else self.branches[(pr["repo"], pr["branch"])]

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> wf.CmdResult:  # noqa: C901
        a = list(argv)
        self.calls.append(a)
        text = str(kwargs.get("input_text") or "")
        if a[0] == "git":
            where, cmd = Path(a[2]), a[3]
            wt = str(where)
            if cmd in ("fetch", "add"):
                if cmd == "add":
                    self.wt_files[wt] = a[5:]
                return wf.CmdResult(0)
            if cmd == "rev-parse":
                if a[5] == "origin/main^{commit}":
                    return wf.CmdResult(0, self.main[self._repo_of_path(where)] + "\n")
                return wf.CmdResult(0, self.wt_head[wt] + "\n")
            if cmd == "worktree":
                if a[4] == "remove":
                    return wf.CmdResult(0)
                path, base = Path(a[7]), a[8]
                repo = self._repo_of_path(where)
                self.wt_repo[str(path)] = repo
                rels = (
                    [wf.RUNTIME_YAML_PATH]
                    if repo == "runtime"
                    else [*wf.PIN_FILES, *wf.LOCK_DIGEST_FILES, *wf.SCOPE_FILES["anchor"]]
                )
                for rel in rels:
                    (path / rel).parent.mkdir(parents=True, exist_ok=True)
                    (path / rel).write_text(self.content(repo, base, rel))
                return wf.CmdResult(0)
            if cmd == "commit":
                sha = self._new_sha()
                self.commits[sha] = {rel: (where / rel).read_text() for rel in self.wt_files[wt]}
                self.wt_head[wt] = sha
                return wf.CmdResult(0)
            if cmd == "diff-tree":
                return wf.CmdResult(0, "\n".join(self.commits[a[-1]]))
            if cmd == "push":
                repo = self.wt_repo[wt]
                lease = next((x for x in a if x.startswith("--force-with-lease=")), None)
                sha, ref = a[-1].split(":", 1)
                key = (repo, ref.removeprefix("refs/heads/"))
                if lease:
                    if self.branches.get(key) != lease.rsplit(":", 1)[1]:
                        return wf.CmdResult(1, "", "stale info")
                elif key in self.branches:
                    return wf.CmdResult(1, "", "non-fast-forward")
                self.branches[key] = sha
                return wf.CmdResult(0)
            if cmd == "show":
                sha, rel = a[4].split(":", 1)
                assert re.fullmatch(r"[0-9a-f]{40}", sha), "never read the index"
                return wf.CmdResult(0, self.content(self._repo_of_path(where), sha, rel))
        if a[0] == "nexus-certify":
            return wf.CmdResult(0, "Issue body: <!-- NEXUS_CORE_EVIDENCE_UNIVERSE: sha256:ab -->\n")
        if a[:3] == ["gh", "issue", "list"]:
            tag = a[a.index("--search") + 1].split(" ")[0]
            hits = [i for i in self.issues if i["repo"] == a[4] and f"[{tag}]" in i["title"]]
            return wf.CmdResult(0, json.dumps(hits))
        if a[:3] == ["gh", "issue", "create"]:
            number = 2000 + len(self.issues)
            title = a[a.index("--title") + 1]
            self.issues.append({"repo": a[4], "number": number, "title": title})
            return wf.CmdResult(0, f"https://github.com/{a[4]}/issues/{number}\n")
        if a[:3] == ["gh", "issue", "comment"]:
            self.comments.append(text)
            return wf.CmdResult(0)
        if a[:3] == ["gh", "pr", "list"]:
            repo, branch = self._repo_of_slug(a[4]), a[a.index("--head") + 1]
            rows = [
                {
                    "number": n,
                    "state": "MERGED" if p["merged"] else "OPEN",
                    "headRefOid": self.head_of(p),
                }
                for n, p in self.prs.items()
                if p["repo"] == repo and p["branch"] == branch
            ]
            return wf.CmdResult(0, json.dumps(rows))
        if a[:3] == ["gh", "pr", "create"]:
            self.next_pr += 1
            branch = a[a.index("--head") + 1]
            self.prs[self.next_pr] = {
                "repo": self._repo_of_slug(a[4]),
                "branch": branch,
                "merged": False,
                "body": text,
                "extra_files": [],
            }
            return wf.CmdResult(0, f"https://github.com/{a[4]}/pull/{self.next_pr}\n")
        if a[:3] == ["gh", "pr", "view"]:
            pr = self.prs[int(a[3])]
            head = self.head_of(pr)
            files = [*self.commits.get(head, {}), *pr["extra_files"]]
            return wf.CmdResult(
                0,
                json.dumps({
                    "number": int(a[3]),
                    "state": "MERGED" if pr["merged"] else "OPEN",
                    "headRefOid": head,
                    "mergeCommit": {"oid": pr["merge"]} if pr["merged"] else None,
                    "files": [{"path": f} for f in files],
                }),
            )
        if a[:3] == ["gh", "pr", "checks"]:
            bucket = "fail" if int(a[3]) in self.red_prs else "pass"
            return wf.CmdResult(0, json.dumps([{"name": "ci", "bucket": bucket}]))
        if a[:3] == ["gh", "pr", "diff"]:
            return wf.CmdResult(0, f"diff for {a[3]}\n")
        if a[:3] == ["gh", "pr", "comment"]:
            return wf.CmdResult(0)
        if a[:2] == ["gh", "api"]:
            if a[2] == "-H":
                match = re.fullmatch(r"repos/([^/]+/[^/]+)/contents/(.+)\?ref=([0-9a-f]{40})", a[4])
                assert match
                repo = self._repo_of_slug(match.group(1))
                return wf.CmdResult(0, self.content(repo, match.group(3), match.group(2)))
            slug = "/".join(a[2].split("/")[1:3])
            return wf.CmdResult(0, self.main[self._repo_of_slug(slug)] + "\n")
        if a[:3] == ["gh", "pr", "merge"]:
            pr = self.prs[int(a[3])]
            head = self.head_of(pr)
            assert a[a.index("--match-head-commit") + 1] == head
            merge_sha = self._new_sha()
            self.commits[merge_sha] = dict(self.commits[head])
            pr.update(merged=True, merge=merge_sha, frozen_head=head)
            self.main[pr["repo"]] = merge_sha
            return wf.CmdResult(0)
        raise AssertionError(f"unexpected command: {a}")


def _world_cfg(tmp_path: Path, **overrides: Any) -> wf.Config:
    return _cfg(
        tmp_path,
        runtime_repo=tmp_path / "runtime-clone",
        nexus_repo=tmp_path / "nexus",
        **overrides,
    )


def _world_deps(world: FakeWorld, reviewer: Any = None, **overrides: Any) -> wf.Deps:
    values: dict[str, Any] = {
        "runner": world,
        "attest_call": lambda _m: _identity_payload(),
        "reviewer": reviewer or (lambda _p: (wf.ACCEPT, ("in scope",))),
        "validator": lambda _t: "",
        "sleep": lambda _s: None,
    }
    values.update(overrides)
    return wf.Deps(**values)


def _state(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "state" / "state.json").read_text())


def test_full_flow_merges_runtime_then_anchor_then_pin(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    reviewed: list[str] = []

    def reviewer(prompt: str) -> tuple[str, tuple[str, ...]]:
        reviewed.append(re.search(r"PR #(\d+) at head (\w+)", prompt).group(0))  # type: ignore[union-attr]
        return wf.ACCEPT, ("in scope",)

    cfg = _world_cfg(tmp_path)
    result = wf.run(cfg, _world_deps(world, reviewer))
    assert result.outcome == "MERGED", result.reason
    merges = [c for c in world.calls if c[:3] == ["gh", "pr", "merge"]]
    assert [(m[3], m[5]) for m in merges] == [
        ("101", wf.RUNTIME_REPO),  # runtime first
        ("103", wf.NEXUS_REPO),  # then the anchor
        ("102", wf.NEXUS_REPO),  # then the pin, rebuilt by the tool on the new main
    ]
    pin_head = world.prs[102]["frozen_head"]
    assert reviewed[-1] == f"PR #102 at head {pin_head}"
    assert (
        pin_head
        == _state(tmp_path)["keys"][next(iter(_state(tmp_path)["keys"]))]["kinds"]["pin"]["head"]
    )
    assert not any(c[:3] == ["gh", "pr", "update-branch"] for c in world.calls)
    pin_body = world.prs[102]["body"]
    assert '"on_merge": "KEEP_OPEN"' in pin_body and "<!-- NEXUS_CORE_ISSUE: 2001 -->" in pin_body
    assert "ONLY when the predecessor is retired" in pin_body  # F3 scope text
    assert "Gateway reload is pending Owner #526 activation" in world.comments[-1]
    assert str(tmp_path) not in world.comments[-1]  # public repo: no local paths
    receipt = json.loads(Path(result.receipt_path).read_text())
    assert set(receipt["merges"]) == {"runtime", "anchor", "pin"}
    assert len(world.issues) == 2
    again = wf.run(cfg, _world_deps(world, reviewer))
    assert again.outcome == "SKIPPED_IDEMPOTENT"


def test_inflight_switch_resumes_after_runtime_merge(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    world.red_prs.add(102)  # the pin PR is red on the first run
    deps = _world_deps(world)
    first = wf.run(_world_cfg(tmp_path), deps)
    assert first.outcome == wf.BLOCKED and first.reason == "PIN_CHECKS_RED:ci"
    state = _state(tmp_path)
    assert state["pending"] and set(state["keys"][state["pending"]]["merges"]) == {
        "runtime",
        "anchor",
    }
    # Runtime main now carries the new default, so a fresh decision would be NOOP;
    # the in-flight switch must resume instead of being forgotten.
    post_merge = tmp_path / "post.yaml"
    post_merge.write_text(state["keys"][state["pending"]]["rendered"])
    world.red_prs.clear()
    second = wf.run(_world_cfg(tmp_path, yaml_path=post_merge), deps)
    assert second.outcome == "MERGED", second.reason
    assert json.loads(Path(second.receipt_path).read_text())["resumed"] is True
    assert sum(c[:3] == ["gh", "pr", "create"] for c in world.calls) == 3  # nothing re-created
    assert sum(c[:3] == ["gh", "issue", "create"] for c in world.calls) == 2
    assert "pending" not in _state(tmp_path)


# ---------------------------------------------------------------- B1: tool-authored scope guard


def test_foreign_commit_on_branch_blocks_merge(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)

    def reviewer(prompt: str) -> tuple[str, tuple[str, ...]]:
        # someone pushes onto the runtime PR branch while it is under review
        key = (
            "runtime",
            next(b for (r, b) in world.branches if r == "runtime"),
        )
        foreign = world._new_sha()
        world.commits[foreign] = dict(world.commits[world.branches[key]])
        world.branches[key] = foreign
        return wf.ACCEPT, ("in scope",)

    result = wf.run(_world_cfg(tmp_path), _world_deps(world, reviewer))
    assert result.outcome == wf.BLOCKED
    assert result.reason.startswith("RUNTIME_")
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in world.calls)


def test_extra_file_in_pr_blocks_merge(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)

    def reviewer(prompt: str) -> tuple[str, tuple[str, ...]]:
        world.prs[101]["extra_files"] = [".github/workflows/ci.yml"]
        return wf.ACCEPT, ("in scope",)

    result = wf.run(_world_cfg(tmp_path), _world_deps(world, reviewer))
    assert result.outcome == wf.BLOCKED
    assert result.reason == "RUNTIME_GUARD_FILE_SCOPE_MISMATCH"
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in world.calls)


def test_reused_pr_with_other_content_blocks(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    world.red_prs.add(101)
    deps = _world_deps(world)
    first = wf.run(_world_cfg(tmp_path), deps)
    assert first.reason == "RUNTIME_CHECKS_RED:ci"
    # the authored head is rewritten in place (same SHA, other bytes served by GitHub)
    head = _state(tmp_path)["keys"][_state(tmp_path)["pending"]]["kinds"]["runtime"]["head"]
    world.commits[head][wf.RUNTIME_YAML_PATH] += "# tampered\n"
    world.red_prs.clear()
    second = wf.run(_world_cfg(tmp_path), deps)
    assert second.outcome == wf.BLOCKED
    assert second.reason == f"RUNTIME_GUARD_CONTENT_MISMATCH:{wf.RUNTIME_YAML_PATH}"
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in world.calls)


def test_unknown_pr_on_branch_is_never_adopted(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    cfg = _world_cfg(tmp_path)
    # Someone else opened a PR on the branch name this tool would use.
    dry = wf.run(_cfg(tmp_path / "dry", dry_run=True), wf.Deps(validator=lambda _t: ""))
    branch = next(s.detail.split(":")[0] for s in dry.plan if s.action == "branch+commit")
    world.branches[("runtime", branch)] = "e" * 40
    world.commits["e" * 40] = {wf.RUNTIME_YAML_PATH: "x"}
    world.prs[50] = {
        "repo": "runtime",
        "branch": branch,
        "merged": False,
        "body": "",
        "extra_files": [],
    }
    result = wf.run(cfg, _world_deps(world))
    assert result.outcome == wf.BLOCKED and result.reason == "RUNTIME_UNKNOWN_PR_ON_BRANCH"
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in world.calls)


# ---------------------------------------------------------------- F2: persisted effects, merged PR


def test_crash_after_pr_creation_finds_pr_and_issue_again(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    world.red_prs.add(101)
    deps = _world_deps(world)
    wf.run(_world_cfg(tmp_path), deps)
    state = _state(tmp_path)
    ctx = state["keys"][state["pending"]]
    assert ctx["kinds"]["runtime"]["pr"] == 101 and ctx["runtime_issue"] == 2000
    # simulate a crash that lost the PR number and Issue number; the PR merged meanwhile
    del ctx["kinds"]["runtime"]["pr"]
    del ctx["runtime_issue"]
    (tmp_path / "state" / "state.json").write_text(json.dumps(state))
    head = world.branches[("runtime", world.prs[101]["branch"])]
    world.commits["9" * 40] = dict(world.commits[head])
    world.prs[101].update(merged=True, merge="9" * 40, frozen_head=head)
    world.main["runtime"] = "9" * 40
    world.red_prs.clear()
    result = wf.run(_world_cfg(tmp_path), deps)
    assert result.outcome == "MERGED", result.reason
    assert sum(c[:3] == ["gh", "issue", "create"] for c in world.calls) == 2  # runtime + pin only
    assert sum(c[:3] == ["gh", "pr", "create"] for c in world.calls) == 3
    assert _state(tmp_path)["keys"][next(iter(_state(tmp_path)["keys"]))]["merges"]["runtime"] == (
        "9" * 40
    )


# ---------------------------------------------------------------- F4: moved base


def test_moved_base_is_rebuilt_by_tool_before_merge(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    moved: list[bool] = []

    def reviewer(prompt: str) -> tuple[str, tuple[str, ...]]:
        if not moved:
            moved.append(True)
            world.main["runtime"] = "a" * 40  # unrelated commit lands on runtime main
        return wf.ACCEPT, ("in scope",)

    result = wf.run(_world_cfg(tmp_path), _world_deps(world, reviewer))
    assert result.outcome == "MERGED", result.reason
    pushes = [c for c in world.calls if c[0] == "git" and c[3] == "push"]
    assert any(x.startswith("--force-with-lease=") for x in pushes[1])  # rebuilt, own lease
    runtime_merge = next(c for c in world.calls if c[:3] == ["gh", "pr", "merge"])
    rebuilt_head = pushes[1][-1].split(":", 1)[0]
    assert runtime_merge[-1] == rebuilt_head == world.prs[101]["frozen_head"]
    assert world.commits[rebuilt_head] == world.commits[pushes[0][-1].split(":", 1)[0]]


def test_scoped_file_changed_on_new_base_blocks(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)

    def reviewer(prompt: str) -> tuple[str, tuple[str, ...]]:
        if world.main["runtime"] != "b" * 40:  # once: main moves and changes the yaml
            new_main = "b" * 40
            world.commits[new_main] = {wf.RUNTIME_YAML_PATH: YAML_FIXTURE.read_text() + "# x\n"}
            world.main["runtime"] = new_main
        return wf.ACCEPT, ("in scope",)

    result = wf.run(_world_cfg(tmp_path), _world_deps(world, reviewer))
    assert result.outcome == wf.BLOCKED
    assert result.reason == "RUNTIME_RUNTIME_BASE_DRIFT"
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in world.calls)


# ---------------------------------------------------------------- F1: resume re-checks the catalog


def test_resume_requires_model_still_served_and_fresh_attestation(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    world.red_prs.add(101)
    clock = [wf._dt.datetime(2026, 10, 13, 6, 0, tzinfo=wf._dt.timezone.utc)]
    attest_calls: list[str] = []

    def attest_call(model: str) -> dict[str, Any]:
        attest_calls.append(model)
        return _identity_payload()

    deps = _world_deps(world, attest_call=attest_call, now=lambda: clock[0])
    assert wf.run(_world_cfg(tmp_path), deps).reason == "RUNTIME_CHECKS_RED:ci"
    assert len(attest_calls) == 1
    # catalog no longer serves the new model -> blocked, nothing merged
    gone = tmp_path / "gone.stdout"
    gone.write_text("gemini-3.9-flash-high\tGemini 3.9 Flash (High)\n")
    blocked = wf.run(_world_cfg(tmp_path, catalog_file=gone), deps)
    assert blocked.reason == "RESUME_NEW_MODEL_NOT_SERVED"
    # still served but the attestation is 25 h old -> re-attested before continuing
    clock[0] += wf._dt.timedelta(hours=25)
    world.red_prs.clear()
    resumed = wf.run(_world_cfg(tmp_path), deps)
    assert resumed.outcome == "MERGED", resumed.reason
    assert len(attest_calls) == 2


def test_stale_attestation_mismatch_on_resume_blocks(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    world.red_prs.add(101)
    clock = [wf._dt.datetime(2026, 10, 13, 6, 0, tzinfo=wf._dt.timezone.utc)]
    payloads = [_identity_payload(), _identity_payload(observed_model="gemini-3.8-flash-high")]
    deps = _world_deps(world, attest_call=lambda _m: payloads.pop(0), now=lambda: clock[0])
    wf.run(_world_cfg(tmp_path), deps)
    clock[0] += wf._dt.timedelta(hours=30)
    world.red_prs.clear()
    result = wf.run(_world_cfg(tmp_path), deps)
    assert result.reason == "RESUME_ATTESTATION:IDENTITY_MISMATCH"
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in world.calls)


# ---------------------------------------------------------------- F5 / F6


def test_show_refuses_non_sha_refs(tmp_path: Path) -> None:
    fake = FakeGh()
    prop = wf.Proposer(wf.GitHub(runner=fake), fake, tmp_path, tmp_path, tmp_path / "w")
    for ref in ("", "HEAD", "origin/main", "abc", "A" * 40):
        with pytest.raises(RuntimeError, match="not_a_commit_sha"):
            prop.show(tmp_path, ref, "pyproject.toml")
    assert not fake.calls


def test_no_required_checks_is_blocked_explicitly() -> None:
    def runner(argv: Sequence[str], **_: Any) -> wf.CmdResult:
        if list(argv[1:3]) == ["pr", "checks"]:
            return wf.CmdResult(1, "", "no required checks reported on the 'x' branch\n")
        return wf.CmdResult(0, json.dumps({"headRefOid": HEAD, "state": "OPEN"}))

    gh = wf.GitHub(runner=runner)
    assert gh.required_checks(wf.NEXUS_REPO, 9) == []
    assert wf.checks_state(gh, wf.NEXUS_REPO, 9, HEAD) == "NO_REQUIRED_CHECKS"
    merged = wf.merge(gh, repo=wf.NEXUS_REPO, pr=9, head=HEAD, review_result=_accept())
    assert merged.reason == "CHECKS_NO_REQUIRED_CHECKS"

    def broken(argv: Sequence[str], **_: Any) -> wf.CmdResult:
        return wf.CmdResult(1, "", "HTTP 502")

    with pytest.raises(RuntimeError):
        wf.GitHub(runner=broken).required_checks(wf.NEXUS_REPO, 9)


# ---------------------------------------------------------------- mutants M4 / M5


def test_m4_head_moving_while_checks_are_read_is_drift() -> None:
    fake = FakeGh()
    fake.heads = [HEAD, "c" * 40]  # first read OK, re-read after the checks shows a new head
    assert wf.checks_state(wf.GitHub(runner=fake), wf.NEXUS_REPO, 9, HEAD) == "HEAD_DRIFT"


def test_m5_unrecorded_accept_never_merges() -> None:
    fake = FakeGh()
    unrecorded = wf.ReviewResult(wf.ACCEPT, ("ok",), HEAD, recorded=False)
    merged = wf.merge(
        wf.GitHub(runner=fake), repo=wf.NEXUS_REPO, pr=9, head=HEAD, review_result=unrecorded
    )
    assert not merged.ok and merged.reason == "REVIEW_NOT_ACCEPT"
    assert not fake.ran("gh", "pr", "merge")


# ---------------------------------------------------------------- B2: sanitizing


def test_malicious_agy_version_never_reaches_yaml() -> None:
    assert wf.safe_agy_version("1.3.4") == "1.3.4"
    for bad in ("1.3.4\nreason: x", "١.٣.٤", "1.3", "v1.3.4", "1.3.4 <!-- x -->", ""):
        assert wf.safe_agy_version(bad) == "unknown"
    catalog = wf.parse_catalog(CATALOG_FIXTURE.read_text(), agy_version="1.3.4'; rm -rf /")
    assert catalog.agy_version == "unknown"
    decision = wf.decide(_policy(), wf.parse_catalog(CATALOG_FIXTURE.read_text()))
    result = wf.render_change(
        YAML_FIXTURE.read_text(),
        decision,
        today=TODAY,
        agy_version="9.9.9\n  injected: true",
        validator=lambda _t: "",
    )
    assert result.ok
    assert "injected" not in result.text
    assert "provider_no_longer_serves_model_agy_unknown_" in result.text


def test_reviewer_reasons_are_sanitized_and_capped() -> None:
    fake = FakeGh()
    reasons = (
        "see /Users/james/.ssh/id_rsa and ~/secrets.txt",
        "token ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "x" * 500,
        *[f"r{i}" for i in range(20)],
    )
    result = wf.review(
        wf.GitHub(runner=fake),
        lambda _p: (wf.REJECT, reasons),
        repo=wf.RUNTIME_REPO,
        pr=7,
        head=HEAD,
        kind="runtime",
        decision=DECISION,
    )
    posted = fake.inputs[-1]
    assert "/Users/james" not in posted and "~/secrets" not in posted and "ghp_" not in posted
    assert len(result.reasons) == wf.MAX_REASONS
    assert all(len(r) <= wf.MAX_REASON_CHARS for r in result.reasons)


# ---------------------------------------------------------------- B3: strict ASCII parsing


def test_non_ascii_digits_and_leading_zeros_are_rejected() -> None:
    for model_id in (
        "gemini-٣.٩-flash-medium",  # Arabic-Indic digits
        "gemini-3.09-flash-medium",  # leading zero
        "gemini-03.9-flash-medium",
        "gemini-3.9-flash-medium\n",
        "gemini-３.9-flash-medium",  # fullwidth digit
    ):
        assert wf.parse_model_id(model_id) is None, model_id
    catalog = wf.parse_catalog(
        "gemini-٣.٩-flash-medium\tGemini ٣.٩ Flash (Medium)\n"
        "gemini-3.09-flash-medium\tGemini 3.9 Flash (Medium)\n"
        "gemini-3.7-flash-medium\tGemini 3.7 Flash (Medium)\n"
    )
    assert [e.model_id for e in catalog.entries] == ["gemini-3.7-flash-medium"]
    assert len(catalog.unrecognized) == 2


def test_duplicate_versions_fail_closed() -> None:
    dup = wf.parse_catalog(
        "gemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"
        "gemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"
    )
    assert not dup.ok and dup.error.startswith("CATALOG_DUPLICATE_VERSION")
    assert wf.decide(_policy(), dup).kind == wf.BLOCKED
