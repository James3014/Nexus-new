#!/usr/bin/env python3
"""Legacy compatibility shim for the pilot chat CLI entrypoint."""

from scripts.nexus_pilot_cli import handle_user_input
from scripts.nexus_pilot_cli import main
from scripts.nexus_pilot_cli import process_repl_line


if __name__ == "__main__":
    raise SystemExit(main())
