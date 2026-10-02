from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _modules(ops_donor: Path, stable_sha: str):
    sys.path.insert(0, str((ops_donor / "scripts" / "ops").resolve()))
    import tg7_github_physical as base
    import tg7_github_physical_v3 as v3
    import tg7_github_physical_v4 as v4

    # The donor scripts are controller tooling, not acceptance evidence. Rebind
    # their exact-subject guards to the immutable standalone Stable subject.
    base.TG7_SUBJECT = stable_sha
    base.TG5_SUBJECT = stable_sha
    v4._install_patches()
    return base, v3


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ops-donor", type=Path, required=True)
    p.add_argument("--stable-subject", type=Path, required=True)
    p.add_argument("--stable-sha", required=True)
    sub = p.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture-tg5")
    capture.add_argument("--receipt", type=Path, required=True)
    capture.add_argument("--provenance", type=Path, required=True)

    collect = sub.add_parser("collect")
    collect.add_argument("--receipt", type=Path, required=True)
    collect.add_argument("--provenance", type=Path, required=True)
    collect.add_argument("--root", type=Path, required=True)
    collect.add_argument("--tar", type=Path, required=True)

    audit = sub.add_parser("audit")
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--junit", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)

    a = p.parse_args()
    subject = a.stable_subject.resolve()
    ops = a.ops_donor.resolve()
    base, v3 = _modules(ops, a.stable_sha)

    if base.git(subject, "rev-parse", "HEAD") != a.stable_sha:
        raise SystemExit("Stable subject HEAD mismatch")

    if a.command == "capture-tg5":
        asyncio.run(
            base._capture_tg5(
                subject,
                a.receipt.resolve(),
                a.provenance.resolve(),
            )
        )
    elif a.command == "collect":
        v3.collect(
            subject,
            subject,
            a.receipt.resolve(),
            a.provenance.resolve(),
            a.root.resolve(),
            a.tar.resolve(),
        )
    else:
        v3.audit(
            subject,
            subject,
            a.root.resolve(),
            a.junit.resolve(),
            a.output.resolve(),
        )


if __name__ == "__main__":
    main()
