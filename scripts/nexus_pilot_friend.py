#!/usr/bin/env python3
import os
import sys

from scripts.nexus_chat_cli import main as pilot_main


DEFAULT_GATEWAY = "http://100.82.155.88:5005"
DEFAULT_PROVIDER = "Gemini"
DEFAULT_MODEL = "gemini-2.5-flash"


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        os.environ["NEXUS_PILOT_TENANT_ID"] = sys.argv[1].strip()

    os.environ.setdefault("NEXUS_PILOT_GATEWAY_URL", DEFAULT_GATEWAY)
    os.environ.setdefault("NEXUS_PILOT_PROVIDER", DEFAULT_PROVIDER)
    os.environ.setdefault("NEXUS_PILOT_MODEL", DEFAULT_MODEL)
    return pilot_main()


if __name__ == "__main__":
    raise SystemExit(main())
