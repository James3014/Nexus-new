#!/usr/bin/env python3
"""Load the frozen v3 Candidate Acceptance validator source."""
from __future__ import annotations

from pathlib import Path

_SOURCE = Path(__file__).with_name("archive") / "validate_acceptance_result_v3_20260915.source.txt"
_CODE = compile(_SOURCE.read_text(encoding="utf-8"), str(_SOURCE), "exec")
exec(_CODE, globals(), globals())
