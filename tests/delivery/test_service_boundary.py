from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    ROOT / "nexus" / "app" / "command_service.py",
}


def _iter_python_files():
    for base in (ROOT / "scripts", ROOT / "nexus"):
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT)
            rel_str = str(rel)
            if "/tests/" in f"/{rel_str}/":
                continue
            if "/archive/" in f"/{rel_str}/":
                continue
            if path.name.endswith(".bak"):
                continue
            yield path


def test_command_service_is_only_runtime_engine_bug_feature_boundary():
    pattern = re.compile(r"engine\.run_(bug|feature)\(")
    offenders: list[str] = []
    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8")
        if pattern.search(text) and path not in ALLOWED:
            offenders.append(str(path))

    assert offenders == [], (
        "Direct engine.run_bug/run_feature calls must stay centralized in "
        f"command_service.py, found: {offenders}"
    )
