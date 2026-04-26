import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

def test_v18_mega_is_retired():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "v1.8_mega.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "has been retired" in result.stderr


def test_v18_feature_bench_is_retired():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "v1.8_feature_bench.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "has been retired" in result.stderr
