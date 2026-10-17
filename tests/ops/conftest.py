from __future__ import annotations

import os
import shutil
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

_DSH_WORKFLOW = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nexus-dsh-workflow"


@pytest.fixture(autouse=True)
def _dsh_skip_host_model_catalog(request, monkeypatch):
    """The #2477 pre-spawn model check reads the host's live Agy catalog cache; DSH tests
    that are not about it must not depend on what the host pool serves today."""
    if request.module.__name__ != "test_nexus_dsh_model_served":
        monkeypatch.setenv("NEXUS_DSH_SKIP_MODEL_CATALOG_CHECK", "1")


@pytest.fixture
def dsh_non_temp_path() -> Path:
    """A directory outside every DSH temp write grant (pytest's tmp_path is inside one).

    DSH workspace-write grants the host temp areas to every session, so the DSH
    workflow guard rejects workspaces there (#1607).
    """
    guard = SourceFileLoader("nexus_dsh_workflow_conftest", str(_DSH_WORKFLOW)).load_module()
    base = Path(
        os.environ.get("NEXUS_DSH_TEST_NON_TEMP_ROOT") or Path.home() / ".cache" / "nexus-dsh-tests"
    )
    try:
        base.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=base)).resolve()
    except OSError as exc:
        pytest.skip(f"no writable non-temp root: {exc}")
    if any(guard._within(root, temp) for temp in guard.dsh_temp_write_roots()):
        shutil.rmtree(root, ignore_errors=True)
        pytest.skip("configured non-temp root is under a DSH temp grant")
    yield root
    shutil.rmtree(root, ignore_errors=True)
