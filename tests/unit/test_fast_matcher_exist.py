import pytest

def test_fast_matcher_module_exists():
    import nexus_core
    assert hasattr(nexus_core, "fast_scan"), "nexus_core should have fast_scan attribute"
    
def test_fast_matcher_metadata_exists():
    import nexus_core
    assert hasattr(nexus_core, "FileMetadata"), "nexus_core should have FileMetadata class"

def test_fast_scan_callable():
    import nexus_core
    # If the function exists, calling it with no args should raise TypeError rather than AttributeError
    with pytest.raises(TypeError):
        nexus_core.fast_scan()
