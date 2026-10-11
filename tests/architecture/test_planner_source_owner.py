from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from tests.architecture._planner_pairs import ALIASABLE_PAIRS, DIVERGENT_PAIRS, PAIRS

ROOT = Path(__file__).resolve().parents[2]


def _runtime_source(module: str) -> str:
    spec = importlib.util.find_spec(module)
    assert spec is not None and spec.origin, module
    return Path(spec.origin).read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"\bnexus_runtime\.(?:planning|support)\.", "nexus.", text)


@pytest.mark.parametrize(("nexus_module", "runtime_module"), ALIASABLE_PAIRS)
def test_planner_shims_point_at_runtime(nexus_module, runtime_module):
    """Step 0 pinned these sources equal to runtime modulo imports; they are now shims."""
    path = ROOT / (nexus_module.replace(".", "/") + ".py")
    text = path.read_text(encoding="utf-8")
    assert f'install_alias(__name__, "{runtime_module}")' in text
    assert len(text.splitlines()) < 30
    assert "if TYPE_CHECKING:" in text  # static re-export for type checkers


def test_no_divergent_pairs_remain():
    """Phase 4b is complete: every pair is an alias, so nothing may stay a full copy."""
    assert DIVERGENT_PAIRS == []


def test_pair_table_covers_27_modules():
    assert len(PAIRS) == 27
