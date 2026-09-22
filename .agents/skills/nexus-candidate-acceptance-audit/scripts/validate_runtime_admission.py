#!/usr/bin/env python3
"""Load the frozen runtime-admission validator source."""

from __future__ import annotations

from pathlib import Path

_SOURCE = Path(__file__).with_name("archive") / "validate_runtime_admission_20260915.source.txt"
_CODE = compile(_SOURCE.read_text(encoding="utf-8"), str(_SOURCE), "exec")
exec(_CODE, globals(), globals())
