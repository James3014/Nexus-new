from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bind_tg5_profile(tg7_subject: Path, tg5_subject: Path) -> None:
    """Force PythonOCIRunner default construction to the exact accepted TG5 profile/lock.

    TG7 is the evidence consumer/reducer.  Its current integration base may carry a
    later uv.lock (for example from TG6), so using TG7's ambient lock would silently
    change the accepted TG5 execution profile.  This bridge keeps the runner class
    implementation from the exact TG7 subject while validating/loading the profile
    manifest, profile lock and uv.lock from the exact TG5 subject.
    """
    sys.path.insert(0, str(tg7_subject))
    from product.execution import python_runner as pr

    profile = pr.PythonOCIProfile.load(
        tg5_subject / "product/execution/profiles/python-oci-pytest-v1.json",
        tg5_subject / "product/execution/profiles/python-oci-pytest-v1.lock",
        tg5_subject / "uv.lock",
    )
    original_init = pr.PythonOCIRunner.__init__

    def bound_init(self, supplied_profile=None):
        return original_init(self, profile if supplied_profile is None else supplied_profile)

    pr.PythonOCIRunner.__init__ = bound_init


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("tg7-collect")
    collect.add_argument("--subject", type=Path, required=True)
    collect.add_argument("--tg5-subject", type=Path, required=True)
    collect.add_argument("--tg5-receipt", type=Path, required=True)
    collect.add_argument("--tg5-provenance", type=Path, required=True)
    collect.add_argument("--root", type=Path, required=True)
    collect.add_argument("--tar", type=Path, required=True)

    audit = sub.add_parser("audit")
    audit.add_argument("--subject", type=Path, required=True)
    audit.add_argument("--tg5-subject", type=Path, required=True)
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--junit", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    subject = args.subject.resolve()
    tg5_subject = args.tg5_subject.resolve()
    _bind_tg5_profile(subject, tg5_subject)

    from tg7_github_physical import _audit, _tg7_collect

    if args.command == "tg7-collect":
        _tg7_collect(
            subject,
            args.tg5_receipt.resolve(),
            args.tg5_provenance.resolve(),
            args.root.resolve(),
            args.tar.resolve(),
        )
    else:
        _audit(
            subject,
            args.root.resolve(),
            args.junit.resolve(),
            args.output.resolve(),
        )


if __name__ == "__main__":
    main()
