import pytest
from nexus.services.local_heal.pre_patch import (
    PatchInputClassifier, 
    PatchInputSanitizer, 
    PrePatchRejectClass, 
    PrePatchInputReceipt
)

def test_prepatch_rejects_refusal_payload():
    classifier = PatchInputClassifier()
    raw_text = "I apologize, but I cannot assist with this code repair task."
    cls = classifier.classify(raw_text)
    assert cls == PrePatchRejectClass.REFUSAL_DETECTED

def test_prepatch_rejects_empty_payload():
    classifier = PatchInputClassifier()
    assert classifier.classify("") == PrePatchRejectClass.EMPTY_RESPONSE
    assert classifier.classify("   ") == PrePatchRejectClass.EMPTY_RESPONSE

def test_prepatch_rejects_missing_patch_body():
    classifier = PatchInputClassifier()
    raw_text = "Here is the explanation, but I forgot the blocks."
    assert classifier.classify(raw_text) == PrePatchRejectClass.MISSING_PATCH_BODY

def test_prepatch_allows_valid_normalized_input():
    classifier = PatchInputClassifier()
    raw_text = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
    assert classifier.classify(raw_text) == PrePatchRejectClass.NONE

def test_prepatch_sanitizer_removes_markdown():
    sanitizer = PatchInputSanitizer()
    raw_text = "```python\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n```"
    clean_text, modified = sanitizer.sanitize(raw_text)
    assert "<<<<<<< SEARCH" in clean_text
    assert "```python" not in clean_text
    assert modified is True

def test_prepatch_receipt_serialization():
    receipt = PrePatchInputReceipt(
        status="REJECTED",
        classification=PrePatchRejectClass.REFUSAL_DETECTED,
        gate_passed=False,
        rejection_reason="Model refused"
    )
    data = receipt.to_dict()
    assert data["classification"] == "refusal_detected"
    assert data["gate_passed"] is False
