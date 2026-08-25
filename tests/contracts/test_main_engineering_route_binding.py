from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "nexus/config/model_workforce.yaml"


def test_online_main_engineering_routes_to_codex_luna() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["route_authority"] == "CapabilityPlanner"
    assert manifest["routing"]["online"]["main_engineering"] == "codex_luna"
    assert manifest["workers"]["codex_luna"]["provider"] == "codex"
    assert "main_engineering" in manifest["workers"]["codex_luna"]["roles"]
