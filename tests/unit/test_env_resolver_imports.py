import pytest
import os
import shutil
from pathlib import Path
from typing import Tuple
from nexus.services.local_heal.env_resolver import EnvResolver, EnvRequirement

def test_probe_python_imports_detects_typing_self():
    # We test that the resolver correctly identifies whether `typing.Self` is supported
    # Python 3.11+ supports it natively. Python 3.9/3.10 does not.
    
    # Locate a python executable to test with
    python_exe = shutil.which("python3")
    if not python_exe:
        pytest.skip("No python3 executable found for testing.")
        
    resolver = EnvResolver()
    
    # Find out actual python version
    version_text = resolver.version_probe(python_exe)
    
    req = EnvRequirement(
        profile="test-typing-self",
        python_candidates=(python_exe,),
        required_imports=("typing.Self",)
    )
    
    resolution = resolver.resolve(req)
    
    # We can't guarantee if the local machine is 3.10 or 3.11+ without parsing the version here,
    # but we can assert the logic of the probe.
    # The actual environment for this workspace is Python 3.14 (from previous context), so it SHOULD be ready.
    if "3.9" in version_text or "3.10" in version_text:
        assert resolution.ready is False
        assert any(p["status"] == "missing_imports" and "missing:typing.Self" in p["import_status"] for p in resolution.probes)
    else:
        assert resolution.ready is True
        assert any(p["status"] == "accepted" for p in resolution.probes)

def test_probe_python_imports_handles_invalid_module():
    python_exe = shutil.which("python3")
    if not python_exe:
        pytest.skip("No python3 executable found for testing.")
        
    resolver = EnvResolver()
    req = EnvRequirement(
        profile="test-invalid",
        python_candidates=(python_exe,),
        required_imports=("this_module_does_not_exist_xyz",)
    )
    
    resolution = resolver.resolve(req)
    
    assert resolution.ready is False
    assert any(p["status"] == "missing_imports" and "missing:this_module_does_not_exist_xyz" in p["import_status"] for p in resolution.probes)
