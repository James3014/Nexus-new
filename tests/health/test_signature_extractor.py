from nexus.health.signature_extractor import FaultSignatureExtractor


def test_signature_extractor_parses_python_traceback_and_hash():
    text = """
Traceback (most recent call last):
  File "nexus/core/commander.py", line 42, in <module>
    import foo
ModuleNotFoundError: No module named 'foo'
"""
    signatures = FaultSignatureExtractor.extract(text)
    assert signatures
    sig = signatures[0]
    assert sig.error_type in {"ModuleNotFoundError"}
    assert len(sig.hash) == 64

