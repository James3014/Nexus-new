import pytest
from nexus.services.local_heal.evidence_compactor import EvidenceCompactor

def test_evidence_compactor_preserves_local_frames():
    evidence = """
    Executing command: python3 reproduce_bug.py
    Traceback (most recent call last):
      File "/opt/homebrew/lib/python3.11/site-packages/django/core/handlers/base.py", line 197, in _get_response
        response = wrapped_callback(request, *callback_args, **callback_kwargs)
      File "/Users/jameschen/Workspace/nexus/.nexus/workspaces/django/django/contrib/auth/validators.py", line 12, in __call__
        raise ValueError("Bug here")
      File "/usr/lib/python3.11/abc.py", line 123, in inner
        return func(*args)
    ValueError: Bug here
    """
    compacted = EvidenceCompactor.compact(evidence, limit=1000)
    
    # 應保留專案內的路徑
    assert "django/contrib/auth/validators.py" in compacted
    # 應保留 Exception
    assert "ValueError: Bug here" in compacted
    # 應移除系統路徑 (如果 Frame 太多)
    # 在本例中 Frame 不多，可能都會保留，但我們可以驗證結構
    assert "Traceback" in compacted

def test_evidence_compactor_short_evidence():
    evidence = "Simple error message"
    compacted = EvidenceCompactor.compact(evidence, limit=100)
    assert compacted == evidence

def test_evidence_compactor_long_non_tb_evidence():
    evidence = "A" * 5000
    compacted = EvidenceCompactor.compact(evidence, limit=1000)
    assert len(compacted) <= 1100 # Allow some margin for truncation marker
    assert compacted.startswith("... [truncated] ...")
