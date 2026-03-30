from __future__ import annotations

import hashlib
import re
from typing import List

from .models import FaultSignature


class FaultSignatureExtractor:
    """Extract deterministic fault signatures from traceback-like text."""

    _TRACEBACK_RE = re.compile(
        r'File "(?P<path>[^"]+)", line (?P<line>\d+), in [^\n]+\n(?P<code>[^\n]*)\n(?P<etype>[A-Za-z_][\w.]*)\s*:\s*(?P<msg>[^\n]+)',
        re.MULTILINE,
    )
    _MODULE_NOT_FOUND_RE = re.compile(r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]")

    @classmethod
    def extract(cls, text: str) -> List[FaultSignature]:
        if not text:
            return []

        signatures: List[FaultSignature] = []
        for match in cls._TRACEBACK_RE.finditer(text):
            path = match.group("path")
            line = int(match.group("line"))
            etype = match.group("etype")
            msg = match.group("msg").strip()
            location = f"{path}:{line}"
            digest = cls._hash(f"{etype}|{location}|{msg}")
            signatures.append(
                FaultSignature(
                    hash=digest,
                    error_type=etype,
                    location=location,
                    traceback_summary=msg[:240],
                )
            )

        for module_name in cls._MODULE_NOT_FOUND_RE.findall(text):
            msg = f"No module named '{module_name}'"
            digest = cls._hash(f"ModuleNotFoundError|unknown:0|{msg}")
            signatures.append(
                FaultSignature(
                    hash=digest,
                    error_type="ModuleNotFoundError",
                    location="unknown:0",
                    traceback_summary=msg,
                )
            )

        dedup: dict[str, FaultSignature] = {sig.hash: sig for sig in signatures}
        return list(dedup.values())

    @staticmethod
    def _hash(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
