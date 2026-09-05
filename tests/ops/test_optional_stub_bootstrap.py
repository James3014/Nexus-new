from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_optional_stubs_do_not_require_heavy_packages_during_conftest_import() -> None:
    probe = textwrap.dedent(
        """
        import builtins
        import importlib.util
        import sys

        blocked = {"numpy", "pandas", "sentence_transformers", "lancedb", "scipy"}
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".", 1)[0]
            if root in blocked:
                raise ModuleNotFoundError(f"No module named '{root}'", name=root)
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import
        spec = importlib.util.spec_from_file_location("nexus_test_conftest", "tests/conftest.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        assert "sentence_transformers" in sys.modules
        assert "lancedb" in sys.modules
        assert "lancedb.pydantic" in sys.modules
        assert "scipy" in sys.modules
        assert "scipy.stats" in sys.modules

        def expect_missing(call, package):
            try:
                call()
            except ModuleNotFoundError as exc:
                assert exc.name == package, (exc.name, package)
            else:
                raise AssertionError(f"expected missing dependency: {package}")

        sentence_transformers = sys.modules["sentence_transformers"]
        lancedb = sys.modules["lancedb"]
        scipy_stats = sys.modules["scipy.stats"]

        expect_missing(
            lambda: sentence_transformers.SentenceTransformer("stub").encode("text"),
            "numpy",
        )
        expect_missing(
            lambda: lancedb.connect("unused").open_table("items").search().to_pandas(),
            "pandas",
        )
        expect_missing(lambda: scipy_stats.norm.cdf(0.0), "numpy")
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
