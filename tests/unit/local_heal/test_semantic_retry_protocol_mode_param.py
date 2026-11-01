"""Semantic retry parses with anchored_edit through an argument, not the process env."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nexus.services.local_heal.context import GovernanceContext, HealContext, OperationalContext
from nexus.services.local_heal.orchestrator import HealOrchestrator

_PATCH = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-def test():\n-    fail\n+def test(): pass"


_REJECTED = SimpleNamespace(kind=SimpleNamespace(name="NO_BLOCKS_FOUND"), message="rejected")


def _run_retry(tmp_path, parse_side_effect=None, parse_return=None):
    orchestrator = HealOrchestrator(phases=[], governance_gate=MagicMock())
    llm = MagicMock()
    llm.generate.return_value = "some response"
    orchestrator._resolve_semantic_retry_llm_client = lambda: llm
    ctx = HealContext(
        op=OperationalContext(instance_id="mode_param", repo_dir=tmp_path, problem_statement="fix"),
        gov=GovernanceContext(),
    )
    ctx.op.final_patch = _PATCH
    ctx.op.model_decisions = [{"phase": "patch", "model": "test-model", "timeout_seconds": 60}]
    env_seen_by_parse = []
    parser = MagicMock()
    parser.classify_format.return_value = "SSRP"

    def _parse(*args, **kwargs):
        env_seen_by_parse.append(os.environ.get("NEXUS_PROTOCOL_MODE"))
        if parse_side_effect is not None:
            raise parse_side_effect
        return parse_return

    parser.parse.side_effect = _parse
    with patch("nexus.services.local_heal.canonical_span.get_canonical_search_span") as span:
        span.return_value = SimpleNamespace(span="def test():\n    fail", source="a.py")
        with patch("nexus.services.local_heal.protocol.SolidSearchReplaceProtocol") as cls:
            cls.return_value = parser
            try:
                orchestrator._attempt_semantic_retry(
                    ctx=ctx, evaluation_report="e", failure_class="verification_failed"
                )
            except RuntimeError:
                pass
    return parser, env_seen_by_parse


@pytest.mark.parametrize("preset", [None, "standard"])
def test_semantic_retry_leaves_protocol_mode_env_untouched_when_parse_raises(
    tmp_path, monkeypatch, preset
):
    if preset is None:
        monkeypatch.delenv("NEXUS_PROTOCOL_MODE", raising=False)
    else:
        monkeypatch.setenv("NEXUS_PROTOCOL_MODE", preset)
    _, seen = _run_retry(tmp_path, parse_side_effect=RuntimeError("parser crashed"))
    assert seen == [preset]
    assert os.environ.get("NEXUS_PROTOCOL_MODE") == preset


def test_semantic_retry_leaves_protocol_mode_env_untouched_when_parse_returns(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("NEXUS_PROTOCOL_MODE", raising=False)
    _, seen = _run_retry(tmp_path, parse_return=_REJECTED)
    assert seen == [None]
    assert "NEXUS_PROTOCOL_MODE" not in os.environ


def test_semantic_retry_parses_with_anchored_edit(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_PROTOCOL_MODE", raising=False)
    parser, _ = _run_retry(tmp_path, parse_return=_REJECTED)
    assert parser.parse.call_count == 1
    assert parser.parse.call_args.kwargs.get("protocol_mode") == "anchored_edit"
