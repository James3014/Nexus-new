"""Routine Gateway deploys and crash restarts need no Owner activation (#2155).

Owner decision 2026-10-14: the #2153 auto-deployer replaces the #526 owner
activation for routine deploys.  The owner-activation / BREAK_GLASS receipts
keep guarding only the manual emergency path (hold -> manual rebind -> adopt
-> release), and an expired receipt must never block a routine reload or a
launchd crash restart.
"""

from __future__ import annotations

import ast
import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.contracts import gateway_deployment
from nexus.orchestrator.execution_readiness import (
    ExecutionReadinessBlockerCode,
)
from scripts.ops import check_gateway_source_drift as drift
from scripts.ops import mcp_gateway_durable as durable
from scripts.ops import nexus_gateway_auto_deploy as deploy
from scripts.ops import workforce_model_autoupdate as autoupdate
from tests.ops.test_nexus_gateway_auto_deploy import (  # noqa: F401 - pytest fixtures
    FakeHost,
    FakeProber,
    _core_origin,
    cfg,
    cycle,
)

ROOT = Path(__file__).resolve().parents[2]
RECEIPT_VALIDATORS = {
    "validate_receipt_freshness",
    "validate_recovery_authority",
    "validate_authority_freshness",
    "validate_host_effect_authority",
    "validate_host_authority",
    "_require_host_authority",
}
RECEIPT_FILES = ("host-authority.json", "recovery-authority.json")


def _names_used(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
    return names


def test_auto_deployer_routine_path_consults_no_owner_activation_receipt():
    """Static guard; the full DEPLOYED cycle with no receipt anywhere is
    tests/ops/test_nexus_gateway_auto_deploy.py::test_green_candidate_is_built_probed_switched_and_receipted.
    """
    source = ROOT / "scripts/ops/nexus_gateway_auto_deploy.py"
    assert not (_names_used(source) & RECEIPT_VALIDATORS)
    text = source.read_text(encoding="utf-8")
    for name in RECEIPT_FILES:
        assert name not in text


def test_routine_reload_succeeds_without_any_authority_receipt(tmp_path, monkeypatch):
    """The auto-deployer's launchd reload reads no receipt, fresh or expired."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("routine reload must not validate an owner-activation receipt")

    for name in (
        "validate_receipt_freshness",
        "validate_recovery_authority",
        "_require_host_authority",
    ):
        if hasattr(durable, name):
            monkeypatch.setattr(durable, name, refuse)
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv[:2])
        return SimpleNamespace(returncode=0, stderr="")

    plist = tmp_path / durable.GATEWAY_PLIST_FILENAME
    durable.reload_gateway_launch_agent(plist, run=run, sleep=lambda _s: None)
    assert calls == [["launchctl", "bootout"], ["launchctl", "bootstrap"]]


def test_crash_restart_is_launchd_keepalive_with_no_receipt_in_the_wrapper(tmp_path):
    config = deploy.Config.default(home=tmp_path)
    previous = plistlib.dumps({
        "Label": deploy.GATEWAY_LABEL,
        "ProgramArguments": ["/bin/zsh", "-c", "true"],
        "KeepAlive": True,
        "RunAtLoad": True,
    })
    root = config.deployments / ("a1-" + "a" * 40)
    python = config.venvs / ("a1-" + "a" * 40) / "bin/python"
    rendered = plistlib.loads(
        deploy.render_plist(previous, deploy.wrapper_command(config, root, python), root)
    )
    assert rendered["KeepAlive"] is True
    assert rendered["RunAtLoad"] is True
    wrapper = " ".join(rendered["ProgramArguments"])
    for marker in (*RECEIPT_FILES, "BREAK_GLASS", "owner_activation", "526"):
        assert marker not in wrapper


def test_expired_owner_activation_receipt_still_fails_closed_for_the_manual_path():
    """Expiry is explicit and keeps guarding the manual #526 fallback only.

    Timestamp rule only; the full manual paths with real receipts are covered by
    tests/ops/test_mcp_gateway_durable.py::test_rollback_missing_observer_and_stale_authority_have_zero_effects
    and tests/contracts/test_gateway_deployment_contract.py (R1 stale authority).
    """
    receipt = object.__new__(gateway_deployment.RecoveryAuthorityReceipt)
    object.__setattr__(receipt, "issued_at", "2026-10-13T09:40:00Z")
    object.__setattr__(receipt, "expires_at", "2026-10-14T09:40:00Z")
    with pytest.raises(gateway_deployment.ContractError, match="stale"):
        gateway_deployment.validate_receipt_freshness(receipt, now="2026-10-15T00:00:00Z")
    doc = gateway_deployment.__doc__ or ""
    assert "#2155" in doc
    assert "manual emergency" in doc


def test_operator_text_no_longer_requires_owner_activation_for_routine_deploys():
    assert "auto-deployer" in drift.REMEDY
    assert "no Owner activation" in drift.REMEDY
    assert "emergency only" in drift.REMEDY
    summary = drift.summarize({
        "verdict": drift.WARN,
        "findings": [{"code": "GATEWAY_BEHIND_MAIN(60)", "severity": drift.WARN}],
    })
    assert drift.REMEDY in summary
    assert "BREAK_GLASS" not in autoupdate.SCOPE_NOTE
    assert "#526" not in autoupdate.SCOPE_NOTE
    from nexus.orchestrator import execution_readiness

    messages = execution_readiness._BLOCKER_MESSAGE  # noqa: SLF001
    rebind = messages[ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED]
    assert "auto-deployer" in rebind
    assert "emergency fallback" in rebind


def test_release_gates_doc_names_the_manual_emergency_sequence():
    text = (ROOT / "docs/ops/release-gates.md").read_text(encoding="utf-8")
    section = text.split("## 🚀 Gateway Deploy Authority (#2155)", 1)[1].split("\n## ", 1)[0]
    for step in ("hold", "adopt", "release", "#526"):
        assert step in section
    assert "no Owner activation" in section


def test_full_deploy_cycle_succeeds_with_expired_owner_activation_receipts(cfg):  # noqa: F811
    """#2155 done-when: expired #526 receipts next to the Gateway never block a routine deploy.

    Both receipts expire before the fake host clock (2025-10-09); the deployer
    never opens them, so their shape does not matter.
    """
    cfg.gateway_root.mkdir(parents=True, exist_ok=True)
    (cfg.gateway_root / "host-authority.json").write_text(
        '{"schema": "host_effect_authority_bundle.v1", "expires_at": "2025-08-24T00:00:00Z"}\n',
        encoding="utf-8",
    )
    (cfg.gateway_root / "recovery-authority.json").write_text(
        '{"schema": "nexus.gateway.durable_recovery_authority.v2",'
        ' "expires_at": "2025-10-01T09:40:00Z"}\n',
        encoding="utf-8",
    )
    result = cycle(cfg, FakeHost(), FakeProber())
    assert result["status"] == "DEPLOYED"
