"""A multi-block patch is applied in full or not at all."""

from __future__ import annotations

import hashlib

from nexus.engine.patch.apply_engine import PatchApplyEngine


def _block(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE\n"


ORIGINAL = "alpha = 1\nbeta = 2\ngamma = 3\n"


def test_patch_with_a_failing_later_block_leaves_the_file_unchanged(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(ORIGINAL, encoding="utf-8")
    patch = _block("alpha = 1", "alpha = 10") + _block("delta = 4", "delta = 40")

    result = PatchApplyEngine(tmp_path).apply_patch("t", "mod.py", patch)

    assert result["success"] is False
    assert target.read_text(encoding="utf-8") == ORIGINAL
    receipt = result["receipt"]
    assert receipt["reason"].startswith("BLOCK_1_FAILED")
    assert [b["status"] for b in receipt["block_results"]] == ["SUCCESS", "FAIL"]
    assert receipt["new_sha"] == hashlib.sha256(ORIGINAL.encode()).hexdigest()


def test_patch_with_every_block_matching_is_written(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(ORIGINAL, encoding="utf-8")
    patch = _block("alpha = 1", "alpha = 10") + _block("gamma = 3", "gamma = 30")

    result = PatchApplyEngine(tmp_path).apply_patch("t", "mod.py", patch)

    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "alpha = 10\nbeta = 2\ngamma = 30\n"
