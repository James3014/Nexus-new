"""#1680 per-phase model tier routing and #1685 repository facts + deterministic tier floors.

Route the phase task, not the DSH session: one cheap, no-tool classifier call through
canonical nexus-agy-dispatch per phase turn, fail open to the session default, never raise
model cost, and floor RED / large-file / oracle-defect repair turns at ``mid``.
"""

from __future__ import annotations

import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pc = SourceFileLoader(
    "nexus_dsh_phase_chain_helpers_for_model_route",
    str(Path(__file__).resolve().with_name("test_nexus_dsh_phase_chain.py")),
).load_module()
rc = SourceFileLoader(
    "nexus_dsh_red_chain_helpers_for_model_route",
    str(Path(__file__).resolve().with_name("test_nexus_dsh_red_chain.py")),
).load_module()
guard = pc.guard


@pytest.fixture
def tmp_path(dsh_non_temp_path: Path) -> Path:
    # DSH grants its temp areas to every session, so the guard rejects workspaces
    # under pytest's tmp_path (#1607); keep these repositories outside them.
    return dsh_non_temp_path


OP_ID = "agyop_" + "1" * 32

FAKE_AGY = (
    """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
argv = sys.argv[1:]
state = Path(os.environ['FAKE_AGY_DIR'])
with (state / 'argv.jsonl').open('a', encoding='utf-8') as fh:
    fh.write(json.dumps(argv) + '\\n')
if '--status' in argv:
    op = argv[argv.index('--status') + 1]
    print(json.dumps({'operation_id': op, 'status': os.environ.get('FAKE_AGY_STATUS', 'COMPLETED'),
                      'stdout_path': str(state / 'out.txt')}))
    sys.exit(0)
if os.environ.get('FAKE_AGY_START_FAIL'):
    sys.exit(3)
count_path = state / 'count'
count = int(count_path.read_text()) if count_path.exists() else 0
count_path.write_text(str(count + 1))
prompt = Path(argv[argv.index('--prompt-file') + 1]).read_text(encoding='utf-8')
(state / f'prompt-{count}.txt').write_text(prompt, encoding='utf-8')
queue = json.loads(os.environ.get('FAKE_AGY_ANSWERS', '[""]'))
(state / 'out.txt').write_text(queue[min(count, len(queue) - 1)], encoding='utf-8')
print(json.dumps({'operation_id': '%s', 'status': 'RUNNING'}))
"""
    % OP_ID
)

PRO_HIGH_PATCH = """- insert:
    - id: nexus-agy-pool-llm
      name: '/opt/dsh/node_modules/@nexus/dsh-llm-agy-pilot/index.js'

- id: agent-default-model
  config:
    provider: nexus-agy-pool
    model: gemini-3.1-pro-high
    reasoningEffort: high
"""

FLASH_LOW_PATCH = """- id: agent-default-model
  config:
    provider: nexus-agy-pool
    model: gemini-3.8-flash
    reasoningEffort: low
"""


def _answer(tier: str, confidence: float = 0.9, reason: str = "r") -> str:
    return json.dumps({"tier": tier, "confidence": confidence, "reason": reason})


def _setup(tmp_path: Path, monkeypatch, patch_text: str | None = PRO_HIGH_PATCH, red=False):
    ctx = rc._setup(tmp_path) if red else pc._setup(tmp_path)
    agy_dir = tmp_path / "agy"
    agy_dir.mkdir()
    agy = tmp_path / "agy-dispatch"
    agy.write_text(FAKE_AGY, encoding="utf-8")
    agy.chmod(0o755)
    for key in ("FAKE_AGY_STATUS", "FAKE_AGY_START_FAIL", "FAKE_AGY_ANSWERS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FAKE_AGY_DIR", str(agy_dir))
    monkeypatch.setenv("NEXUS_AGY_DISPATCH", str(agy))
    patch = None
    if patch_text is not None:
        patch = tmp_path / "session.patch.yml"
        patch.write_text(patch_text, encoding="utf-8")
    ctx.update(agy=agy, agy_dir=agy_dir, patch=patch, monkeypatch=monkeypatch)
    return ctx


def _answers(ctx: dict, *answers: str) -> None:
    ctx["monkeypatch"].setenv("FAKE_AGY_ANSWERS", json.dumps(list(answers)))


def _patch_args(ctx: dict) -> list[str]:
    return ["--patch", str(ctx["patch"])] if ctx["patch"] is not None else []


def _run(ctx: dict, *extra: str, phase: str = "green", plan=None, code: int = 0) -> dict:
    plan = plan or [{"session": "s-1"}]
    proc = pc._start(ctx, plan, *_patch_args(ctx), *extra, phase=phase)
    assert proc.returncode == code, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _auto(ctx: dict, *answers: str, phase: str = "green", extra=(), plan=None) -> dict:
    _answers(ctx, *answers)
    return _run(ctx, "--model-route", "auto", *extra, phase=phase, plan=plan)


def _agy_argvs(ctx: dict) -> list[list[str]]:
    path = ctx["agy_dir"] / "argv.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _prompt(ctx: dict, index: int = 0) -> str:
    return (ctx["agy_dir"] / f"prompt-{index}.txt").read_text(encoding="utf-8")


def _patches(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, arg in enumerate(argv) if arg == "--patch"]


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"x_{i} = {i}\n" for i in range(count)), encoding="utf-8")


def _contract(ctx: dict, text: str) -> None:
    ctx["contract"].write_text(text, encoding="utf-8")


# --- #1680: route off ---------------------------------------------------------------------


def test_route_off_by_default_leaves_argv_unchanged_and_never_classifies(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _answers(ctx, _answer("light"))
    out = _run(ctx)
    (argv,) = pc._calls(ctx)
    assert argv[:4] == ["--profile", "headless", "--patch", str(ctx["patch"])]
    assert argv[4] == "--json"
    assert _patches(argv) == [str(ctx["patch"])]
    assert _agy_argvs(ctx) == []
    route = out["route"]
    assert route["mode"] == "off"
    assert route["tier"] is None and route["classifier_operation_id"] is None
    assert route["floor_reason"] is None
    assert not (ctx["state"] / "routes").exists()


def test_route_off_explicit_patch_override_is_authoritative(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch, patch_text=FLASH_LOW_PATCH)
    out = _run(ctx, "--model-route", "off")
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]
    assert (out["route"]["mode"], out["route"]["model"], out["route"]["effort"]) == (
        "off",
        "gemini-3.8-flash",
        "low",
    )


# --- #1680: each tier ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "model", "effort"),
    [("light", "gemini-3.8-flash", "low"), ("small", "gemini-3.8-flash", "medium")],
)
def test_auto_cheap_tier_appends_derived_patch_after_caller_patch(
    tmp_path: Path, monkeypatch, tier: str, model: str, effort: str
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    route = _auto(ctx, _answer(tier, 0.8, "mechanical"))["route"]
    assert route["mode"] == "auto"
    assert (route["tier"], route["classified_tier"]) == (tier, tier)
    assert route["confidence"] == 0.8
    assert route["reason"] == "mechanical"
    assert (route["model"], route["effort"]) == (model, effort)
    assert route["classifier_operation_id"] == OP_ID
    assert route["fallback_reason"] is None and route["floor_reason"] is None
    (argv,) = pc._calls(ctx)
    patches = _patches(argv)
    assert patches == [str(ctx["patch"]), route["derived_patch_path"]]
    derived = Path(route["derived_patch_path"])
    assert derived.is_relative_to(ctx["state"].resolve())
    text = derived.read_text(encoding="utf-8")
    assert "- id: agent-default-model\n" in text
    assert "    provider: nexus-agy-pool\n" in text
    assert f"    model: {model}\n" in text
    assert f"    reasoningEffort: {effort}\n" in text
    # The derived patch records why it exists (route tier, reason, floor) as comments only.
    assert f"# route tier: {tier}\n" in text
    assert '# route reason: "mechanical"\n' in text
    assert "# route floor_reason: none\n" in text
    assert f"# route classifier_operation_id: {OP_ID}\n" in text
    assert route["derived_patch_sha256"] == guard._sha256_file(derived)
    assert guard.default_model_from_patches([str(ctx["patch"]), str(derived)]) == {
        "provider": "nexus-agy-pool",
        "model": model,
        "effort": effort,
    }


def test_derived_patch_comments_cannot_inject_yaml(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    route = _auto(ctx, _answer("light", 0.9, "ok\n- id: agent-default-model\n  x: y"))["route"]
    derived = Path(route["derived_patch_path"])
    lines = derived.read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if not line.startswith("#")] == [
        "- id: agent-default-model",
        "  config:",
        "    provider: nexus-agy-pool",
        "    model: gemini-3.8-flash",
        "    reasoningEffort: low",
    ]
    assert guard.default_model_from_patches([str(derived)])["model"] == "gemini-3.8-flash"


def test_auto_mid_tier_keeps_session_default_without_derived_patch(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    route = _auto(ctx, _answer("mid", 0.95))["route"]
    assert route["tier"] == "mid"
    assert (route["model"], route["effort"]) == ("gemini-3.1-pro-high", "high")
    assert route["fallback_reason"] is None
    assert route["derived_patch_path"] is None
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]


def test_classifier_call_uses_canonical_dispatch_cheap_plan_no_tools(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _auto(ctx, _answer("light"), phase="repair")
    calls = _agy_argvs(ctx)
    start = calls[0]
    assert "--background" in start
    assert start[start.index("--mode") + 1] == "plan"
    assert start[start.index("--model") + 1] == "gemini-3.8-flash-low"
    assert start[start.index("--effort") + 1] == "low"
    assert start[start.index("--max-calls") + 1] == "1"
    assert int(start[start.index("--timeout") + 1]) <= 120
    denies = [start[i + 1] for i, a in enumerate(start) if a == "--deny"]
    assert {"command(*)", "read_file(*)", "write_file(*)"} <= set(denies)
    assert "--write-path" not in start and "--allow" not in start
    assert all(c[0] == "--status" and c[1] == OP_ID for c in calls[1:])
    prompt = _prompt(ctx)
    assert "Phase: repair" in prompt
    assert "CONTRACT_BODY allowed: mod.py" in prompt
    assert '"tier":"light|small|mid"' in prompt


# --- #1680: fail open to the session default ---------------------------------------------


def test_low_confidence_falls_back_to_default(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    route = _auto(ctx, _answer("light", 0.49))["route"]
    assert route["classified_tier"] == "light"
    assert route["model"] == "gemini-3.1-pro-high"
    assert route["fallback_reason"] == "LOW_CONFIDENCE"
    assert route["derived_patch_path"] is None
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("not json at all", "CLASSIFIER_ANSWER_MALFORMED"),
        ("", "CLASSIFIER_ANSWER_MALFORMED"),
        ('{"tier":"light"}', "CLASSIFIER_ANSWER_MALFORMED"),
        ('{"tier":"light","confidence":1.5,"reason":"x"}', "CLASSIFIER_ANSWER_MALFORMED"),
        ('{"tier":"light","confidence":true,"reason":"x"}', "CLASSIFIER_ANSWER_MALFORMED"),
        ('{"tier":"light","confidence":0.9,"reason":7}', "CLASSIFIER_ANSWER_MALFORMED"),
        (
            '{"tier":"light","confidence":0.9,"reason":"x","model":"y"}',
            "CLASSIFIER_ANSWER_MALFORMED",
        ),
        (
            '{"tier":"light","confidence":0.9,"reason":"x"} {"tier":"mid"}',
            "CLASSIFIER_ANSWER_MALFORMED",
        ),
        ('["light"]', "CLASSIFIER_ANSWER_MALFORMED"),
        ('{"tier":"top","confidence":0.9,"reason":"x"}', "TIER_UNKNOWN"),
        ('{"tier":"huge","confidence":0.9,"reason":"x"}', "TIER_UNKNOWN"),
    ],
)
def test_malformed_or_unknown_answer_fails_open_to_default(
    tmp_path: Path, monkeypatch, answer: str, reason: str
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    out = _auto(ctx, answer)
    route = out["route"]
    assert route["fallback_reason"] == reason
    assert (route["model"], route["effort"]) == ("gemini-3.1-pro-high", "high")
    assert route["derived_patch_path"] is None
    assert route["classifier_operation_id"] == OP_ID
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]
    assert out["dsh_exit_code"] == 0


def test_fenced_json_answer_is_accepted(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    route = _auto(ctx, "```json\n" + _answer("light") + "\n```\n")["route"]
    assert route["tier"] == "light" and route["fallback_reason"] is None


@pytest.mark.parametrize(
    ("env", "reason", "op_id"),
    [
        ({"FAKE_AGY_START_FAIL": "1"}, "CLASSIFIER_DISPATCH_FAILED", None),
        ({"FAKE_AGY_STATUS": "FAILED"}, "CLASSIFIER_OPERATION_FAILED", OP_ID),
        ({"FAKE_AGY_STATUS": "OUTCOME_UNKNOWN"}, "CLASSIFIER_OPERATION_FAILED", OP_ID),
        ({"FAKE_AGY_STATUS": "RUNNING"}, "CLASSIFIER_TIMEOUT", OP_ID),
    ],
)
def test_classifier_dispatch_errors_fail_open_to_default(
    tmp_path: Path, monkeypatch, env: dict[str, str], reason: str, op_id: str | None
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    route = _auto(ctx, _answer("light"), extra=("--route-classifier-timeout", "1"))["route"]
    assert route["fallback_reason"] == reason
    assert route["classifier_operation_id"] == op_id
    assert route["tier"] is None
    assert route["model"] == "gemini-3.1-pro-high"
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]


@pytest.mark.parametrize(
    ("requested", "dispatched"),
    [(None, "45"), ("0.5", "1"), ("0.01", "1"), ("1", "1"), ("44.5", "45"), ("120", "120")],
)
def test_canonical_dispatch_timeout_is_at_least_one_whole_second(
    tmp_path: Path, monkeypatch, requested: str | None, dispatched: str
) -> None:
    # A sub-second --route-classifier-timeout must never reach the dispatcher as
    # `--timeout 0`; the default (A/B-measured) 45s path is unchanged.
    ctx = _setup(tmp_path, monkeypatch)
    extra = () if requested is None else ("--route-classifier-timeout", requested)
    route = _auto(ctx, _answer("light"), extra=extra)["route"]
    assert route["fallback_reason"] is None
    start = _agy_argvs(ctx)[0]
    assert start[start.index("--timeout") + 1] == dispatched


def test_fractional_classifier_deadline_still_fails_open_to_default(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_AGY_STATUS", "RUNNING")
    route = _auto(ctx, _answer("light"), extra=("--route-classifier-timeout", "0.2"))["route"]
    assert route["fallback_reason"] == "CLASSIFIER_TIMEOUT"
    assert route["model"] == "gemini-3.1-pro-high"
    start = _agy_argvs(ctx)[0]
    assert start[start.index("--timeout") + 1] == "1"
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]


def test_missing_dispatcher_binary_fails_open(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("NEXUS_AGY_DISPATCH", str(tmp_path / "absent"))
    route = _auto(ctx, _answer("light"))["route"]
    assert route["fallback_reason"] == "CLASSIFIER_DISPATCH_FAILED"
    assert route["model"] == "gemini-3.1-pro-high"


def test_unknown_session_default_model_skips_classifier(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch, patch_text=None)
    route = _auto(ctx, _answer("light"))["route"]
    assert route["fallback_reason"] == "DEFAULT_MODEL_UNKNOWN"
    assert route["model"] is None
    assert route["classifier_operation_id"] is None
    assert _agy_argvs(ctx) == []
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == []


def test_non_agy_pool_session_default_is_not_rerouted(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(
        tmp_path, monkeypatch, patch_text=PRO_HIGH_PATCH.replace("nexus-agy-pool", "other-llm")
    )
    route = _auto(ctx, _answer("light"))["route"]
    assert route["fallback_reason"] == "DEFAULT_PROVIDER_UNSUPPORTED"
    assert _agy_argvs(ctx) == []
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]


# --- #1680: never raises cost ---------------------------------------------------------------


def test_never_raises_cost_above_cheaper_session_default(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch, patch_text=FLASH_LOW_PATCH)
    route = _auto(ctx, _answer("small"))["route"]
    assert route["classified_tier"] == "small"
    assert (route["model"], route["effort"]) == ("gemini-3.8-flash", "low")
    assert route["fallback_reason"] == "NOT_CHEAPER_THAN_DEFAULT"
    assert route["derived_patch_path"] is None


def test_route_table_override_cannot_raise_cost(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    table = tmp_path / "table.json"
    table.write_text(
        json.dumps({"light": {"model": "gemini-3.1-pro-high", "effort": "high"}}),
        encoding="utf-8",
    )
    route = _auto(ctx, _answer("light"), extra=("--route-table", str(table)))["route"]
    assert route["fallback_reason"] == "NOT_CHEAPER_THAN_DEFAULT"
    assert route["model"] == "gemini-3.1-pro-high"


def test_route_table_override_maps_tier(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    table = tmp_path / "table.json"
    table.write_text(
        json.dumps({"small": {"model": "gemini-3.8-flash", "effort": "low"}}), encoding="utf-8"
    )
    route = _auto(ctx, _answer("small"), extra=("--route-table", str(table)))["route"]
    assert (route["model"], route["effort"]) == ("gemini-3.8-flash", "low")
    assert route["fallback_reason"] is None
    assert route["route_table_sha256"] == guard._sha256_file(table)


@pytest.mark.parametrize(
    "table",
    [
        {"top": {"model": "gemini-3.1-pro-high", "effort": "high"}},
        {"light": {"model": "gemini-3.8-flash", "effort": "extreme"}},
        {"light": {"model": "", "effort": "low"}},
        {"light": {"model": "gemini-3.8-flash"}},
        {"light": {"model": "bad model\nid: x", "effort": "low"}},
        ["light"],
    ],
)
def test_invalid_route_table_blocks_before_dsh(tmp_path: Path, monkeypatch, table) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    path = tmp_path / "table.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    _answers(ctx, _answer("light"))
    out = _run(ctx, "--model-route", "auto", "--route-table", str(path), code=guard.EXIT_BLOCKED)
    assert out["reason_code"] == "ROUTE_TABLE_INVALID"
    assert pc._calls(ctx) == []
    assert _agy_argvs(ctx) == []


def test_route_table_requires_auto(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    table = tmp_path / "table.json"
    table.write_text("{}", encoding="utf-8")
    out = _run(ctx, "--route-table", str(table), code=guard.EXIT_BLOCKED)
    assert out["reason_code"] == "ROUTE_ARGUMENT_INVALID"
    assert pc._calls(ctx) == []


@pytest.mark.parametrize("timeout", ["0", "-1", "121"])
def test_invalid_classifier_timeout_blocks_before_dsh(
    tmp_path: Path, monkeypatch, timeout: str
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    out = _run(
        ctx,
        "--model-route",
        "auto",
        "--route-classifier-timeout",
        timeout,
        code=guard.EXIT_BLOCKED,
    )
    assert out["reason_code"] == "ROUTE_ARGUMENT_INVALID"
    assert pc._calls(ctx) == []


@pytest.mark.parametrize(
    ("candidate", "default", "cheaper"),
    [
        (("gemini-3.8-flash", "low"), ("gemini-3.1-pro-high", "high"), True),
        (("gemini-3.8-flash", "medium"), ("gemini-3.1-pro-low", "low"), True),
        (("gemini-3.8-flash", "medium"), ("gemini-3.8-flash", "low"), False),
        (("gemini-3.8-flash", "low"), ("gemini-3.8-flash", "low"), False),
        (("gemini-3.1-pro-high", "high"), ("gemini-3.8-flash", "medium"), False),
        (("mystery-model", "low"), ("gemini-3.1-pro-high", "high"), False),
        (("gemini-3.8-flash", "low"), ("mystery-model", "high"), False),
        (("gemini-3.8-flash", "low"), ("gemini-3.1-pro-high", None), True),
        (("gemini-3.8-flash", "low"), ("gemini-3.1-pro", None), False),
        (("gemini-3.8-flash-high", "low"), ("gemini-3.1-pro-high", "high"), False),
    ],
)
def test_strictly_cheaper_requires_known_cost_order(candidate, default, cheaper) -> None:
    assert guard.is_strictly_cheaper(candidate[0], candidate[1], default[0], default[1]) is cheaper


def test_session_default_is_last_patch_and_rejects_expressions(tmp_path: Path) -> None:
    first = tmp_path / "a.yml"
    first.write_text(PRO_HIGH_PATCH, encoding="utf-8")
    second = tmp_path / "b.yml"
    second.write_text(FLASH_LOW_PATCH, encoding="utf-8")
    assert guard.default_model_from_patches([str(first), str(second)]) == {
        "provider": "nexus-agy-pool",
        "model": "gemini-3.8-flash",
        "effort": "low",
    }
    assert guard.default_model_from_patches([str(first)])["model"] == "gemini-3.1-pro-high"
    expr = tmp_path / "c.yml"
    expr.write_text(FLASH_LOW_PATCH.replace("gemini-3.8-flash", "!!js process.env.M"), "utf-8")
    assert guard.default_model_from_patches([str(expr)])["model"] is None
    assert guard.default_model_from_patches([str(tmp_path / "absent.yml")])["model"] is None


# --- #1680: determinism, durability, observation ------------------------------------------


def test_route_decision_is_deterministic_replay() -> None:
    table = guard.load_route_table(None)
    kwargs = dict(
        answer_text=_answer("small", 0.7, "reads code"),
        classifier_error=None,
        classifier_operation_id=OP_ID,
        table=table,
        default_model="gemini-3.1-pro-high",
        default_effort="high",
        floor_tier=None,
        floor_reason=None,
    )
    first = guard.decide_route(**kwargs)
    assert first == guard.decide_route(**kwargs)
    assert first["tier"] == "small" and first["model"] == "gemini-3.8-flash"
    assert first["decision_inputs_sha256"].startswith("sha256:")
    other = guard.decide_route(**{**kwargs, "answer_text": _answer("light", 0.7, "reads code")})
    assert other["decision_inputs_sha256"] != first["decision_inputs_sha256"]
    floored = guard.decide_route(**{**kwargs, "floor_tier": "mid", "floor_reason": "RED_PHASE"})
    assert floored["decision_inputs_sha256"] != first["decision_inputs_sha256"]
    assert guard.build_classifier_prompt("green", "C", []) == guard.build_classifier_prompt(
        "green", "C", []
    )


def test_route_receipt_is_durable_and_hash_bound(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    route = _auto(ctx, _answer("light"))["route"]
    receipt_path = Path(route["receipt_path"])
    assert receipt_path.is_relative_to(ctx["state"].resolve())
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == "nexus.dsh_model_route.v1"
    assert receipt["phase"] == "green"
    assert receipt["classifier_answer_raw"] == _answer("light")
    assert receipt["phase_contract_sha256"] == guard._sha256_file(ctx["contract"])
    assert receipt["classifier_prompt_sha256"].startswith("sha256:")
    assert receipt["named_files"] == [{"path": "mod.py", "lines": 1}]
    body = {k: v for k, v in receipt.items() if k != "receipt_hash"}
    assert receipt["receipt_hash"] == guard._sha256_bytes(
        guard._canonical_json(body).encode("utf-8")
    )
    for key in (
        "mode",
        "tier",
        "confidence",
        "reason",
        "model",
        "effort",
        "classifier_operation_id",
        "fallback_reason",
        "floor_reason",
    ):
        assert receipt[key] == route[key]
    assert route["receipt_hash"] == receipt["receipt_hash"]


def test_route_observation_reports_latency_and_never_invents_tokens_or_cost(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    out = _auto(ctx, _answer("light"))
    obs = out["route"]["observation"]
    assert isinstance(obs["classifier_wall_ms"], int) and obs["classifier_wall_ms"] >= 0
    assert obs["classifier_prompt_chars"] > 0
    assert obs["classifier_prompt_chars_unit"] == "characters"
    assert obs["tokens"] is None and obs["cost"] is None
    assert obs["cost_evidence"] == "NOT_OBSERVED"
    assert isinstance(out["phase_wall_ms"], int) and out["phase_wall_ms"] >= 0


def test_blocked_preflight_never_classifies(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    payload = pc._doctor_payload()
    payload["resume_disposition"] = "UNSAFE"
    ctx["doctor"].write_text(
        f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({payload!r}))\n", encoding="utf-8"
    )
    _answers(ctx, _answer("light"))
    out = _run(ctx, "--model-route", "auto", code=guard.EXIT_BLOCKED)
    assert out["decision"] == "BLOCK_RESUME"
    assert _agy_argvs(ctx) == []
    assert pc._calls(ctx) == []


# --- #1685: repository facts in the classifier prompt ------------------------------------


def test_classifier_prompt_lists_named_file_line_counts_and_total(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _write_lines(ctx["repo"] / "scripts" / "ops" / "tool", 40)
    _write_lines(ctx["repo"] / "tests" / "ops" / "test_tool.py", 12)
    _contract(
        ctx,
        "Write one test in `tests/ops/test_tool.py::test_busy` for scripts/ops/tool.\n"
        "Do not touch scripts/ops/missing.py or ../outside.py or /etc/hosts.\n",
    )
    _auto(ctx, _answer("small"))
    prompt = _prompt(ctx)
    assert "- scripts/ops/tool: 40 lines\n" in prompt
    assert "- tests/ops/test_tool.py: 12 lines\n" in prompt
    assert "Total: 52 lines" in prompt
    assert "missing.py" not in prompt.split("PHASE CONTRACT")[0]
    assert "outside.py" not in prompt.split("PHASE CONTRACT")[0]
    assert "/etc/hosts:" not in prompt
    assert "reading load" in prompt


def test_named_files_stay_inside_the_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    _write_lines(repo / "scripts" / "a.py", 3)
    outside = tmp_path / "secret.py"
    _write_lines(outside, 2000)
    (repo / "scripts" / "link.py").symlink_to(outside)
    (repo / "scripts" / "dir.py").mkdir()
    text = (
        "scripts/a.py scripts/a.py. scripts/link.py scripts/dir.py "
        "scripts/../../secret.py /scripts/a.py .git/config"
    )
    assert guard.named_repository_files(repo, text) == [{"path": "scripts/a.py", "lines": 3}]


def test_no_named_files_is_stated_in_prompt() -> None:
    prompt = guard.build_classifier_prompt("green", "edit something", [])
    assert "Named repository files: (none found)" in prompt


# --- #1685: deterministic tier floors -------------------------------------------------------


def test_large_named_file_floors_route_at_mid(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _write_lines(ctx["repo"] / "scripts" / "ops" / "nexus-agy-dispatch", 1501)
    _contract(ctx, "Add one assertion to scripts/ops/nexus-agy-dispatch.\n")
    route = _auto(ctx, _answer("small", 0.95, "one small edit"))["route"]
    assert route["classified_tier"] == "small"
    assert route["tier"] == "mid"
    assert route["floor_reason"] == "LARGE_FILE:scripts/ops/nexus-agy-dispatch=1501"
    assert route["fallback_reason"] is None
    assert (route["model"], route["effort"]) == ("gemini-3.1-pro-high", "high")
    assert route["derived_patch_path"] is None
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]
    assert "- scripts/ops/nexus-agy-dispatch: 1501 lines\n" in _prompt(ctx)


def test_file_at_threshold_does_not_floor(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _write_lines(ctx["repo"] / "scripts" / "edge.py", 1500)
    _contract(ctx, "Rename a constant in scripts/edge.py.\n")
    route = _auto(ctx, _answer("light", 0.95))["route"]
    assert (route["tier"], route["floor_reason"]) == ("light", None)
    assert route["model"] == "gemini-3.8-flash"


def test_red_phase_floors_route_at_mid(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _contract(ctx, "Write one failing test in test_mod.py.\n")
    plan = [{"session": "s-red", "goal": True}]
    route = _auto(
        ctx,
        _answer("small", 0.95, "one test"),
        phase="red",
        extra=("--goal-objective", "FIX_1678"),
        plan=plan,
    )["route"]
    assert route["classified_tier"] == "small"
    assert route["tier"] == "mid"
    assert route["floor_reason"] == "RED_PHASE"
    assert route["model"] == "gemini-3.1-pro-high"
    assert route["derived_patch_path"] is None
    (argv,) = pc._calls(ctx)
    assert _patches(argv) == [str(ctx["patch"])]


@pytest.mark.parametrize("code", ["RED_ORACLE_DEFECT", "UNINTENDED_FAILURE"])
def test_repair_with_oracle_defect_feedback_floors_at_mid(
    tmp_path: Path, monkeypatch, code: str
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _contract(
        ctx, f"Fix mod.py.\n\nGATE FEEDBACK\nReason codes: {code}, TARGET_TESTS_NOT_PASSING\n"
    )
    route = _auto(ctx, _answer("light", 0.95), phase="repair")["route"]
    assert route["classified_tier"] == "light"
    assert route["tier"] == "mid"
    assert route["floor_reason"] == f"REPAIR_GATE_FEEDBACK:{code}"
    assert route["model"] == "gemini-3.1-pro-high"
    assert route["derived_patch_path"] is None


def test_repair_without_oracle_feedback_keeps_classified_tier(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _contract(ctx, "Fix mod.py.\nReason codes: TARGET_TESTS_NOT_PASSING\n")
    route = _auto(ctx, _answer("light", 0.95), phase="repair")["route"]
    assert (route["tier"], route["floor_reason"]) == ("light", None)
    assert route["model"] == "gemini-3.8-flash"


def test_oracle_defect_words_do_not_floor_green_phase(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _contract(ctx, "Avoid RED_ORACLE_DEFECT style mistakes in mod.py.\n")
    route = _auto(ctx, _answer("light", 0.95))["route"]
    assert (route["tier"], route["floor_reason"]) == ("light", None)


def test_small_file_green_phase_can_still_route_to_flash(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _write_lines(ctx["repo"] / "scripts" / "small.py", 80)
    _contract(ctx, "Change one default in scripts/small.py.\n")
    route = _auto(ctx, _answer("small", 0.9))["route"]
    assert (route["tier"], route["floor_reason"]) == ("small", None)
    assert (route["model"], route["effort"]) == ("gemini-3.8-flash", "medium")
    (argv,) = pc._calls(ctx)
    assert _patches(argv)[-1] == route["derived_patch_path"]


def test_floor_never_raises_cost_above_cheap_session_default(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch, patch_text=FLASH_LOW_PATCH)
    _write_lines(ctx["repo"] / "scripts" / "big.py", 3000)
    _contract(ctx, "Edit scripts/big.py.\n")
    route = _auto(ctx, _answer("light", 0.95))["route"]
    assert route["tier"] == "mid"
    assert (route["model"], route["effort"]) == ("gemini-3.8-flash", "low")
    assert route["derived_patch_path"] is None


def test_floor_is_recorded_when_classifier_fails_open(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _write_lines(ctx["repo"] / "scripts" / "big.py", 1600)
    _contract(ctx, "Edit scripts/big.py.\n")
    route = _auto(ctx, "garbage")["route"]
    assert route["fallback_reason"] == "CLASSIFIER_ANSWER_MALFORMED"
    assert route["floor_reason"] == "LARGE_FILE:scripts/big.py=1600"
    assert route["model"] == "gemini-3.1-pro-high"


@pytest.mark.parametrize(
    ("phase", "text", "files", "expected"),
    [
        ("green", "x", [], (None, None)),
        ("red", "x", [], ("mid", "RED_PHASE")),
        (
            "red",
            "x",
            [{"path": "a", "lines": 1501}, {"path": "b", "lines": 2}],
            ("mid", "RED_PHASE;LARGE_FILE:a=1501"),
        ),
        ("repair", "UNINTENDED_FAILURE", [], ("mid", "REPAIR_GATE_FEEDBACK:UNINTENDED_FAILURE")),
        ("repair", "NOT_UNINTENDED_FAILURES", [], (None, None)),
        ("green", "RED_ORACLE_DEFECT", [], (None, None)),
    ],
)
def test_route_floor_is_pure_and_deterministic(phase, text, files, expected) -> None:
    assert guard.route_floor(phase, text, files) == expected


# --- #1680/#1685: chain summaries -----------------------------------------------------------


def test_chain_records_route_per_turn_and_routes_each_phase_afresh(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch, red=True)
    _answers(ctx, _answer("light", 0.95, "red is small"), _answer("light", 0.9, "one-liner"))
    plan = [
        rc._red("s-red", rc.GOOD_TEST, goal=True),
        {"session": "s-green", "write": pc._value(3)},
    ]
    proc = rc._start_red(
        ctx,
        plan,
        *_patch_args(ctx),
        "--model-route",
        "auto",
        "--goal-objective",
        "FIX_1678",
        *rc._green_args(ctx),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "GREEN_READY"
    assert out["model_route"] == "auto"
    red_entry, green_entry = out["phases"]
    assert red_entry["route"]["tier"] == "mid"
    assert red_entry["route"]["floor_reason"] == "RED_PHASE"
    assert red_entry["route"]["model"] == "gemini-3.1-pro-high"
    assert red_entry["route"] == red_entry["run"]["route"]
    assert green_entry["route"]["tier"] == "light"
    assert green_entry["route"]["model"] == "gemini-3.8-flash"
    assert green_entry["route"]["floor_reason"] is None
    red_argv, green_argv = pc._calls(ctx)
    assert _patches(red_argv) == [str(ctx["patch"])]
    assert _patches(green_argv) == [str(ctx["patch"]), green_entry["route"]["derived_patch_path"]]
    assert "Phase: red" in _prompt(ctx, 0) and "Phase: green" in _prompt(ctx, 1)
    # Bindings carry no route identity; lineage is unchanged.
    binding = guard.load_binding(ctx["state"], "s-green")
    assert binding["parent_session_id"] == "s-red"
    assert not any("route" in key for key in binding)


def test_chain_route_off_records_off_and_never_classifies(tmp_path: Path, monkeypatch) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    plan = [
        {"session": "s-green", "write": pc._value(2)},
        {"session": "s-r1", "write": pc._value(3)},
    ]
    proc = pc._start(
        ctx,
        plan,
        *_patch_args(ctx),
        "--green-contract",
        str(ctx["green"]),
        "--auto-repair",
        "1",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["model_route"] == "off"
    assert [p["route"]["mode"] for p in out["phases"]] == ["off", "off"]
    assert _agy_argvs(ctx) == []
    for argv in pc._calls(ctx):
        assert _patches(argv) == [str(ctx["patch"])]


def test_chain_repair_turn_is_classified_with_its_gate_feedback(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _setup(tmp_path, monkeypatch)
    _answers(ctx, _answer("small", 0.9), _answer("light", 0.9))
    plan = [
        {"session": "s-green", "write": pc._value(2)},
        {"session": "s-r1", "write": pc._value(3)},
    ]
    proc = pc._start(
        ctx,
        plan,
        *_patch_args(ctx),
        "--model-route",
        "auto",
        "--green-contract",
        str(ctx["green"]),
        "--auto-repair",
        "1",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "GREEN_READY"
    green_entry, repair_entry = out["phases"]
    assert (green_entry["route"]["tier"], repair_entry["route"]["tier"]) == ("small", "light")
    repair_prompt = _prompt(ctx, 1)
    assert "Phase: repair" in repair_prompt
    assert "GREEN GATE FEEDBACK" in repair_prompt
    assert "TARGET_TESTS_NOT_PASSING" in repair_prompt
