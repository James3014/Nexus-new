from __future__ import annotations

from nexus.services.local_heal.local_model_patch_envelope import parse_local_model_patch_envelope


def test_parse_patch_envelope_missing_diff() -> None:
    raw = "Here is my advice: you should look at line 12."
    envelope = parse_local_model_patch_envelope("t1", raw)
    assert envelope.parser_status == "blocked"
    assert envelope.parser_error == "missing_unified_diff"
    assert envelope.unified_diff == ""
    assert envelope.candidate_hash == ""
    assert envelope.public_claim_allowed is False


def test_parse_patch_envelope_markdown_diff() -> None:
    raw = """
Some description.
```diff
--- a/main.py
+++ b/main.py
@@ -1,3 +1,3 @@
-print("hello")
+print("world")
```
End.
"""
    envelope = parse_local_model_patch_envelope("t2", raw)
    assert envelope.parser_status == "pass"
    assert "print(\"world\")" in envelope.unified_diff
    assert envelope.target_file == "main.py"
    assert envelope.candidate_hash != ""
    assert envelope.public_claim_allowed is False
