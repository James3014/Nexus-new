from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "ops" / "nexus-grok-accounts"


def _fake_grok(
    path: Path,
    *,
    login_fail: bool = False,
    models_fail: bool = False,
) -> Path:
    script = path / "fake-grok"
    script.write_text(
        f"""#!/usr/bin/env python3
import os
import sys

LOGIN_FAIL = {str(login_fail)}
MODELS_FAIL = {str(models_fail)}

if any(
    key in os.environ
    for key in ("XAI_API_KEY", "GROK_API_KEY", "NEXUS_GROK_API_KEY")
):
    print("ambient credential leaked", file=sys.stderr)
    raise SystemExit(9)

if sys.argv[1:] == ["login", "--device-code"]:
    print("To sign in, open this URL in your browser:")
    print("  https://accounts.x.ai/oauth2/device?user_code=TEST-CODE")
    print("Confirm this code in your browser:")
    print("  TEST-CODE")
    if LOGIN_FAIL:
        print("authorization expired")
        raise SystemExit(1)
    print("✓ Signed in as test-account@example.invalid")
    raise SystemExit(0)

if sys.argv[1:] == ["models"]:
    if MODELS_FAIL:
        print("Error: Not signed in.")
        raise SystemExit(1)
    print("You are logged in with grok.com.")
    print("Default model: grok-4.7")
    print("Available models:")
    print("  * grok-4.7 (default)")
    raise SystemExit(0)

print("unexpected command", sys.argv, file=sys.stderr)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "NEXUS_GROK_ACCOUNTS_SNAPSHOT": str(ROOT),
        "NEXUS_GROK_ACCOUNT_POOL_ROOT": str(tmp_path / "pool"),
        "NEXUS_GROK_PROFILE_ROOT": str(tmp_path / "profiles"),
    })
    return env


def _run(
    tmp_path: Path,
    *args: str,
    login_fail: bool = False,
    models_fail: bool = False,
    extra_env: dict[str, str] | None = None,
):
    fake = _fake_grok(
        tmp_path,
        login_fail=login_fail,
        models_fail=models_fail,
    )
    env = _env(tmp_path)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(CLI), "--grok-bin", str(fake), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_onboard_registers_only_after_login_and_models_probe(tmp_path: Path) -> None:
    proc = _run(tmp_path, "onboard", "--alias", "grok-02", "--json")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout[proc.stdout.rfind("{") :])
    assert payload["status"] == "REGISTERED"
    assert payload["alias"] == "grok-02"
    assert "display_label" not in payload
    assert "test-account@example.invalid" not in proc.stdout
    assert payload["models"] == ["grok-4.7"]

    state_path = tmp_path / "pool" / "state.json"
    state = json.loads(state_path.read_text())
    assert state["accounts"]["grok-02"]["display_label"] == "test-account@example.invalid"
    assert state_path.stat().st_mode & 0o077 == 0
    assert (tmp_path / "profiles" / "grok-02").stat().st_mode & 0o077 == 0


def test_onboard_strips_ambient_provider_credentials(tmp_path: Path) -> None:
    proc = _run(
        tmp_path,
        "onboard",
        "--alias",
        "grok-02",
        extra_env={
            "XAI_API_KEY": "x",
            "GROK_API_KEY": "x",
            "NEXUS_GROK_API_KEY": "x",
        },
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ambient credential leaked" not in proc.stdout + proc.stderr


def test_failed_device_login_never_registers_account(tmp_path: Path) -> None:
    proc = _run(
        tmp_path,
        "onboard",
        "--alias",
        "grok-02",
        login_fail=True,
    )

    assert proc.returncode == 2
    state_path = tmp_path / "pool" / "state.json"
    assert not state_path.exists()


def test_failed_models_probe_never_registers_account(tmp_path: Path) -> None:
    proc = _run(
        tmp_path,
        "onboard",
        "--alias",
        "grok-02",
        models_fail=True,
    )

    assert proc.returncode == 2
    assert not (tmp_path / "pool" / "state.json").exists()


def test_list_omits_raw_identity_and_home_path_by_default(tmp_path: Path) -> None:
    proc = _run(tmp_path, "onboard", "--alias", "grok-02")
    assert proc.returncode == 0

    listed = _run(tmp_path, "list", "--json")
    assert listed.returncode == 0
    payload = json.loads(listed.stdout)
    assert payload[0]["alias"] == "grok-02"
    assert "display_label" not in payload[0]
    assert "test-account@example.invalid" not in listed.stdout
    assert "home_path" not in payload[0]
    assert str(tmp_path / "profiles" / "grok-02") not in listed.stdout


def test_list_can_show_local_identity_only_when_explicit(tmp_path: Path) -> None:
    proc = _run(tmp_path, "onboard", "--alias", "grok-02")
    assert proc.returncode == 0

    listed = _run(tmp_path, "list", "--show-identities", "--json")

    assert listed.returncode == 0
    payload = json.loads(listed.stdout)
    assert payload[0]["display_label"] == "test-account@example.invalid"


def test_health_reports_default_model_policy_mismatch_without_mutating_pool(
    tmp_path: Path,
) -> None:
    onboard = _run(tmp_path, "onboard", "--alias", "grok-02")
    assert onboard.returncode == 0
    before = (tmp_path / "pool" / "state.json").read_bytes()

    health = _run(
        tmp_path,
        "health",
        "--alias",
        "grok-02",
        "--json",
    )

    assert health.returncode == 2
    payload = json.loads(health.stdout)
    assert payload[0]["status"] == "MODEL_POLICY_MISMATCH"
    assert payload[0]["expected_model"] == "grok-4.5"
    assert payload[0]["models"] == ["grok-4.7"]
    assert "display_label" not in payload[0]
    assert "test-account@example.invalid" not in health.stdout
    assert (tmp_path / "pool" / "state.json").read_bytes() == before


def test_duplicate_provider_identity_is_rejected(tmp_path: Path) -> None:
    first = _run(tmp_path, "onboard", "--alias", "grok-02")
    assert first.returncode == 0

    second = _run(tmp_path, "onboard", "--alias", "grok-03")

    assert second.returncode == 2
    assert "DISPLAY_LABEL_DUPLICATE" in second.stderr
    state = json.loads((tmp_path / "pool" / "state.json").read_text())
    assert sorted(state["accounts"]) == ["grok-02"]
