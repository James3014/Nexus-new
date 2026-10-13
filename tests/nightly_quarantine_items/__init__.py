"""Per-entry nightly quarantine data (Refs #1897), one module per entry.

Every entry names exact test ids that failed in the scheduled Tier 3 run
38240112497 (2026-10-12). tests/conftest.py marks them xfail(strict=False)
only when NEXUS_NIGHTLY_QUARANTINE=1, which the nightly job sets. Other runs
(PR impact gate, local) are unaffected. A quarantined test that starts
passing shows up as XPASS: remove its id here in the same change.

Layout: each entry is its own module in this package defining ``ENTRY`` with
the keys file, disposition, issue, cause, tests. Adding or removing an entry
touches only that entry's file, so parallel PRs do not conflict textually.

Naming rule: the module name is the entry's ``file`` path without ``.py``,
lower-cased, with every run of non-[a-z0-9] characters replaced by ``_``
(tests/app/test_research_flow_service.py -> tests_app_test_research_flow_service.py).
One entry per test file; tests/ops/test_nightly_quarantine_items_layout.py
enforces the rule. Modules are assembled in sorted module-name order into
``QUARANTINE``. tests/nightly_quarantine_entries.py is a thin shim that
re-exports it, so tests.nightly_quarantine.load_quarantine() is unchanged.

Add / remove convention: to add an entry, create its module. To remove one,
set ``ENTRY = None`` (a tombstone) with a one-line comment saying why; NEVER
delete the file, because Nexus Core's deletion_policy=FORBID would then require
an Owner-signed deletion manifest. A tombstone contributes nothing to
``QUARANTINE``; if the same test file is quarantined again, put its ``ENTRY``
back in the same module. A periodic Owner-signed batch can prune tombstones.

disposition: quarantine | delete-candidate | quarantine-product-bug?
issue: the tracking Issue ("#N") that owns the fix-or-delete decision; every
entry needs a cause and a real Issue number.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path


def _assemble() -> tuple[dict[str, object], ...]:
    names = sorted(
        info.name
        for info in pkgutil.iter_modules([str(Path(__file__).parent)])
        if not info.name.startswith("_")
    )
    entries = (importlib.import_module(f"{__name__}.{name}").ENTRY for name in names)
    return tuple(entry for entry in entries if entry is not None)


QUARANTINE: tuple[dict[str, object], ...] = _assemble()
