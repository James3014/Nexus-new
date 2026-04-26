#!/usr/bin/env python3
import sys


DEPRECATION_MESSAGE = (
    "scripts/v1.8_feature_bench.py has been retired. "
    "Use canonical Nexus entrypoints via scripts/engine/nexus_cli.py instead."
)


def main() -> int:
    print(DEPRECATION_MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
