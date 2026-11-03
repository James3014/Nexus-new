"""#3236: the pregate scratch copy is handed to the model sandbox as a PinnedRoot."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import replace

import nexus.engine.model_output_sandbox as model_sandbox_module
import nexus.executors.cli_worker as cli_worker
from nexus.core.contained_write import PinnedRoot
from nexus.engine import cli_pregate
from nexus.engine.model_output_sandbox import SANDBOX_EXEC


def test_pregate_scratch_is_passed_to_the_sandbox_as_a_pinned_root(tmp_path, monkeypatch):
    seen = []
    real = cli_worker.run_cli_worker

    @contextmanager
    def fake_sandbox(work_dir, *, readable=()):
        seen.append((work_dir, os.stat(os.fspath(work_dir), follow_symlinks=False)))
        yield [SANDBOX_EXEC, "-p", "(version 1)"], {"HOME": os.fspath(work_dir)}

    monkeypatch.setattr(model_sandbox_module, "model_sandbox", fake_sandbox)
    monkeypatch.setattr(
        cli_worker,
        "run_cli_worker",
        lambda request, **kw: real(replace(request, seatbelt_profile=None), **kw),
    )
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("print(1)\n", encoding="utf-8")

    passed, results = cli_pregate.run_cli_pregate(
        root, [f"{sys.executable} -c pass"], isolate_workspace=True
    )

    assert passed, results
    work_dir, info = seen[0]
    assert isinstance(work_dir, PinnedRoot)
    assert tuple(work_dir.identity) == (info.st_dev, info.st_ino)
