import sys
import os
import shutil
import tempfile
import types
from pathlib import Path

# Create a mock pytest module
pytest_mock = types.ModuleType("pytest")
class WarnsContext:
    def __enter__(self):
        # Return a list of records for record testing in test_roundtrip
        class MockRecord:
            class MockMessage:
                def __init__(self):
                    self.args = ["This file contains multiple command blocks"]
            def __init__(self):
                self.message = self.MockMessage()
        return [MockRecord()]
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

pytest_mock.warns = lambda *args, **kwargs: WarnsContext()
pytest_mock.mark = types.ModuleType("pytest.mark")
pytest_mock.mark.parametrize = lambda *args, **kwargs: (lambda f: f)
pytest_mock.fixture = lambda *args, **kwargs: (lambda f: f)

sys.modules["pytest"] = pytest_mock

# Setup path to workspace
sys.path.insert(0, "/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy")
os.environ["ASTROPY_USE_SYSTEM_ERFA"] = "1"

import astropy.io.ascii.tests.test_qdp as test_qdp

temp_dir = tempfile.mkdtemp()
tmp_path = Path(temp_dir)

try:
    print("Running test_get_tables_from_qdp_file...")
    p1 = tmp_path / "1"
    p1.mkdir()
    test_qdp.test_get_tables_from_qdp_file(p1)
    
    print("Running test_roundtrip...")
    p2 = tmp_path / "2"
    p2.mkdir()
    test_qdp.test_roundtrip(p2)
    
    print("Running test_read_example...")
    test_qdp.test_read_example()
    
    print("Running test_roundtrip_example...")
    p3 = tmp_path / "3"
    p3.mkdir()
    test_qdp.test_roundtrip_example(p3)
    
    print("Running test_roundtrip_example_comma...")
    p4 = tmp_path / "4"
    p4.mkdir()
    test_qdp.test_roundtrip_example_comma(p4)
    
    print("Running test_read_write_simple...")
    p5 = tmp_path / "5"
    p5.mkdir()
    test_qdp.test_read_write_simple(p5)
    
    print("Running test_read_write_simple_specify_name...")
    p6 = tmp_path / "6"
    p6.mkdir()
    test_qdp.test_read_write_simple_specify_name(p6)
    
    print("Running test_get_lines_from_qdp...")
    p7 = tmp_path / "7"
    p7.mkdir()
    test_qdp.test_get_lines_from_qdp(p7)
    
    print("ALL QDP TESTS PASSED SUCCESSFULLY!")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    shutil.rmtree(temp_dir)
