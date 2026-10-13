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
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
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

    fake = FakeGh()
    fake.open_prs = [{"number": 41, "headRefOid": HEAD}]
    prop = wf.Proposer(wf.GitHub(runner=fake), fake, tmp_path, tmp_path, tmp_path / "w")
    assert prop.open_pr(wf.RUNTIME_REPO, "auto/x", "t", "b") == (41, HEAD)
    assert not fake.ran("gh", "pr", "create")


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
    """git + gh + nexus-certify fake for the whole propose/review/merge/notify chain."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.red_prs: set[int] = set()
        self.calls: list[list[str]] = []
        self.prs: dict[int, dict[str, Any]] = {}
        self.next_pr = 100
        self.staged: dict[str, list[str]] = {}
        self.comments: list[str] = []

    def _pr(self, number: int) -> dict[str, Any]:
        return self.prs[number]

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> wf.CmdResult:
        a = list(argv)
        self.calls.append(a)
        text = str(kwargs.get("input_text") or "")
        if a[0] == "git":
            repo, cmd = Path(a[2]), a[3]
            if cmd in ("fetch", "commit", "push"):
                return wf.CmdResult(0)
            if cmd == "worktree" and a[4] == "add":
                path = Path(a[7])
                src = (
                    {wf.RUNTIME_YAML_PATH: YAML_FIXTURE}
                    if "runtime" in path.name
                    else {
                        rel: REPO_ROOT / rel
                        for rel in (*wf.PIN_FILES, *wf.LOCK_DIGEST_FILES, *wf.SCOPE_FILES["anchor"])
                    }
                )
                for rel, origin in src.items():
                    (path / rel).parent.mkdir(parents=True, exist_ok=True)
                    (path / rel).write_bytes(origin.read_bytes())
                return wf.CmdResult(0)
            if cmd == "add":
                self.staged[str(repo)] = a[5:]
                return wf.CmdResult(0)
            if cmd == "diff":
                return wf.CmdResult(0, "\n".join(self.staged[str(repo)]))
            if cmd == "rev-parse":
                return wf.CmdResult(0, HEAD + "\n")
            if cmd == "show":
                ref, rel = a[4].split(":", 1)
                if repo.name == "runtime-clone":
                    wt = self.tmp / "state" / "work"
                    found = list(wt.glob(f"*/runtime/{rel}"))
                    return wf.CmdResult(0, found[0].read_text())
                if ref == "origin/main":
                    return wf.CmdResult(0, (REPO_ROOT / rel).read_text())
                found = list((self.tmp / "state" / "work").glob(f"*/nexus-pin/{rel}"))
                return wf.CmdResult(0, found[0].read_text())
        if a[0] == "nexus-certify":
            return wf.CmdResult(0, "Issue body: <!-- NEXUS_CORE_EVIDENCE_UNIVERSE: sha256:ab -->\n")
        if a[:3] == ["gh", "issue", "create"]:
            return wf.CmdResult(0, f"https://github.com/{a[4]}/issues/2000\n")
        if a[:3] == ["gh", "issue", "comment"]:
            self.comments.append(text)
            return wf.CmdResult(0)
        if a[:3] == ["gh", "pr", "list"]:
            return wf.CmdResult(0, "[]")
        if a[:3] == ["gh", "pr", "create"]:
            self.next_pr += 1
            branch = a[a.index("--head") + 1]
            self.prs[self.next_pr] = {"head": HEAD, "merged": False, "branch": branch, "body": text}
            return wf.CmdResult(0, f"https://github.com/{a[4]}/pull/{self.next_pr}\n")
        if a[:3] == ["gh", "pr", "view"]:
            pr = self._pr(int(a[3]))
            return wf.CmdResult(
                0,
                json.dumps({
                    "number": int(a[3]),
                    "state": "MERGED" if pr["merged"] else "OPEN",
                    "headRefOid": pr["head"],
                    "mergeCommit": {"oid": f"{int(a[3]):040d}"} if pr["merged"] else None,
                }),
            )
        if a[:3] == ["gh", "pr", "checks"]:
            bucket = "fail" if int(a[3]) in self.red_prs else "pass"
            return wf.CmdResult(0, json.dumps([{"name": "ci", "bucket": bucket}]))
        if a[:3] == ["gh", "pr", "diff"]:
            return wf.CmdResult(0, f"diff for {a[3]}\n")
        if a[:3] == ["gh", "pr", "comment"]:
            return wf.CmdResult(0)
        if a[:3] == ["gh", "pr", "merge"]:
            pr = self._pr(int(a[3]))
            assert a[a.index("--match-head-commit") + 1] == pr["head"]
            pr["merged"] = True
            return wf.CmdResult(0)
        if a[:3] == ["gh", "pr", "update-branch"]:
            self._pr(int(a[3]))["head"] = "9" * 40
            return wf.CmdResult(0)
        raise AssertionError(f"unexpected command: {a}")


def test_full_flow_merges_runtime_then_anchor_then_pin(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    reviewed: list[str] = []

    def reviewer(prompt: str) -> tuple[str, tuple[str, ...]]:
        reviewed.append(re.search(r"PR #(\d+) at head (\w+)", prompt).group(0))  # type: ignore[union-attr]
        return wf.ACCEPT, ("in scope",)

    cfg = _cfg(tmp_path, runtime_repo=tmp_path / "runtime-clone", nexus_repo=tmp_path / "nexus")
    deps = wf.Deps(
        runner=world,
        attest_call=lambda _m: _identity_payload(),
        reviewer=reviewer,
        validator=lambda _t: "",
        sleep=lambda _s: None,
    )
    result = wf.run(cfg, deps)
    assert result.outcome == "MERGED", result.reason
    merges = [c for c in world.calls if c[:3] == ["gh", "pr", "merge"]]
    assert [(m[3], m[5]) for m in merges] == [
        ("101", wf.RUNTIME_REPO),  # runtime first
        ("103", wf.NEXUS_REPO),  # then the anchor
        ("102", wf.NEXUS_REPO),  # then the pin, on its updated head
    ]
    assert reviewed[-1] == f"PR #102 at head {'9' * 40}"
    pin_body = world.prs[102]["body"]
    assert '"on_merge": "KEEP_OPEN"' in pin_body and "<!-- NEXUS_CORE_ISSUE: 2000 -->" in pin_body
    assert "Gateway reload is pending Owner #526 activation" in world.comments[-1]
    receipt = json.loads(Path(result.receipt_path).read_text())
    assert set(receipt["merges"]) == {"runtime", "anchor", "pin"}
    # the same state again creates nothing new
    again = wf.run(cfg, deps)
    assert again.outcome == "SKIPPED_IDEMPOTENT"


def test_inflight_switch_resumes_after_runtime_merge(tmp_path: Path) -> None:
    world = FakeWorld(tmp_path)
    world.red_prs.add(102)  # the pin PR is red on the first run
    cfg = _cfg(tmp_path, runtime_repo=tmp_path / "runtime-clone", nexus_repo=tmp_path / "nexus")
    deps = wf.Deps(
        runner=world,
        attest_call=lambda _m: _identity_payload(),
        reviewer=lambda _p: (wf.ACCEPT, ("in scope",)),
        validator=lambda _t: "",
        sleep=lambda _s: None,
    )
    first = wf.run(cfg, deps)
    assert first.outcome == wf.BLOCKED and first.reason == "PIN_CHECKS_RED:ci"
    state = json.loads((tmp_path / "state" / "state.json").read_text())
    assert state["pending"] and set(state["keys"][state["pending"]]["merges"]) == {
        "runtime",
        "anchor",
    }
    # Runtime main now carries the new default, so a fresh decision would be NOOP;
    # the in-flight switch must resume instead of being forgotten.
    post_merge = tmp_path / "post.yaml"
    post_merge.write_text(state["keys"][state["pending"]]["rendered"])
    world.red_prs.clear()
    second = wf.run(
        _cfg(
            tmp_path,
            runtime_repo=tmp_path / "runtime-clone",
            nexus_repo=tmp_path / "nexus",
            yaml_path=post_merge,
        ),
        deps,
    )
    assert second.outcome == "MERGED", second.reason
    assert json.loads(Path(second.receipt_path).read_text())["resumed"] is True
    assert sum(c[:3] == ["gh", "pr", "create"] for c in world.calls) == 3  # nothing re-created
    assert "pending" not in json.loads((tmp_path / "state" / "state.json").read_text())
