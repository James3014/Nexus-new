import pytest
import re
from pathlib import Path

def test_forbidden_imports():
    """🛡️ 確保底層 (core/services) 不會循環導入高層 (engine/app)"""
    core_dir = Path("nexus/core")
    for py_file in core_dir.glob("**/*.py"):
        content = py_file.read_text()
        # core 不應導入 engine
        assert "from nexus.engine" not in content
        assert "import nexus.engine" not in content
        # core 不應導入 app
        assert "from nexus.app" not in content
        assert "import nexus.app" not in content

def test_engine_layer_rules():
    """⚙️ engine 可以導入 core 和 services，但不能導入 app"""
    engine_dir = Path("nexus/engine")
    for py_file in engine_dir.glob("**/*.py"):
        content = py_file.read_text()
        assert "from nexus.app" not in content
        assert "import nexus.app" not in content
