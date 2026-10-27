"""Test helper for #2936: model-output commands on a host without an OS barrier.

Production refuses to run local-model output when there is no OS sandbox (Linux, or
``NEXUS_DISABLE_OS_SANDBOX=1``). Tests of drone and local_heal *logic* still need their
commands to run on Linux CI, so files that use this fixture replace the sandbox with a
pass-through on such a host only. Where a barrier exists (macOS) the real sandbox stays on.
The sandbox contract itself (no network, no writes outside the work dir, nothing runs without
a barrier) is proven by ``tests/engine/test_model_output_sandbox_2936.py`` on both kinds of
host; never use this fixture there.
"""

from __future__ import annotations

import contextlib
import os

import pytest

from nexus.engine import model_output_sandbox
from nexus.engine.sandboxed_lane import os_sandbox_available


@pytest.fixture(scope="module")
def model_exec_without_barrier_runs_unconfined():
    # Module scope: class- and module-scoped fixtures in these files run the pipeline once and
    # must already see the pass-through.
    if os_sandbox_available():
        yield
        return

    @contextlib.contextmanager
    def passthrough(work_dir, *, readable=(), writable=()):
        yield [], dict(os.environ)

    # The product canary memoizes whole runs; a result computed under the refusing sandbox by an
    # earlier module must not leak into this one, nor ours into later modules.
    from nexus.services.product_capability_canary_helper import _run_canary_mainchain_cached

    _run_canary_mainchain_cached.cache_clear()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(model_output_sandbox, "model_sandbox", passthrough)
        yield
    _run_canary_mainchain_cached.cache_clear()
