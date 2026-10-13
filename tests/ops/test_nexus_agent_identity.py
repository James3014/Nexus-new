from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from scripts.ops import nexus_agent_identity as ident

OPENSSL = shutil.which("openssl")
pytestmark = pytest.mark.skipif(OPENSSL is None, reason="openssl required")

TOKEN = "ghs_" + "T" * 36


def _iso(delta_s: float) -> str:
    t = datetime.now(timezone.utc) + timedelta(seconds=delta_s)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def app(tmp_path, monkeypatch):
    d = tmp_path / "apps"
    d.mkdir(mode=0o700)
    subprocess.run(
        [OPENSSL, "genrsa", "-out", str(d / "agent.pem"), "2048"], check=True, capture_output=True
    )
    (d / "agent.json").write_text(json.dumps({"id": 4242}))
    os.chmod(d / "agent.pem", 0o600)
    os.chmod(d / "agent.json", 0o600)
    monkeypatch.setenv("NEXUS_AGENT_APP_DIR", str(d))
    monkeypatch.setattr(ident, "OPENSSL", OPENSSL)
    monkeypatch.setattr(ident, "OPENSSL_ENFORCE_OWNER", False)
    return d


@pytest.fixture
def fake(monkeypatch):
    state = {
        "calls": [],
        "installs": [
            {"id": 1, "account": {"login": "other"}},
            {"id": 77, "account": {"login": "James3014"}},
        ],
        "expires": _iso(3600),
    }

    def http(method, path, bearer):
        state["calls"].append((method, path, bearer))
        if path == "/app/installations":
            return state["installs"]
        if path.endswith("/access_tokens"):
            return {"token": TOKEN, "expires_at": state["expires"]}
        if path == "/app":
            return {"slug": "nexus-agent-james3014"}
        if path == "/installation/repositories":
            return {"total_count": 3}
        raise AssertionError(path)

    monkeypatch.setattr(ident, "http", http)
    return state


def test_jwt_header_claims_and_signature(app, tmp_path):
    now = 1_800_000_000
    jwt = ident.make_jwt(app, now=now)
    h, c, s = jwt.split(".")
    pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
    assert json.loads(base64.urlsafe_b64decode(pad(h))) == {"alg": "RS256", "typ": "JWT"}
    claims = json.loads(base64.urlsafe_b64decode(pad(c)))
    assert claims == {"iat": now - 60, "exp": now + 540, "iss": "4242"}
    pub = tmp_path / "pub.pem"
    subprocess.run(
        [OPENSSL, "rsa", "-in", str(app / "agent.pem"), "-pubout", "-out", str(pub)],
        check=True,
        capture_output=True,
    )
    sig = tmp_path / "sig"
    sig.write_bytes(base64.urlsafe_b64decode(pad(s)))
    ok = subprocess.run(
        [OPENSSL, "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig)],
        input=f"{h}.{c}".encode(),
        capture_output=True,
    )
    assert ok.returncode == 0


def test_openssl_ownership_enforced_by_default(tmp_path):
    f = tmp_path / "openssl"
    f.write_text("#!/bin/sh\n")
    f.chmod(0o755)
    if os.getuid() != 0:
        with pytest.raises(ident.IdentityError, match="root-owned"):
            ident.check_openssl(str(f))
    f.chmod(0o775)
    with pytest.raises(ident.IdentityError, match="writable"):
        ident.check_openssl(str(f), enforce_owner=False)
    with pytest.raises(ident.IdentityError, match="not found"):
        ident.check_openssl(str(tmp_path / "nope"))


def test_make_jwt_enforces_owner_by_default(app, monkeypatch):
    monkeypatch.setattr(ident, "OPENSSL_ENFORCE_OWNER", True)
    if os.stat(OPENSSL).st_uid != 0:
        with pytest.raises(ident.IdentityError, match="root-owned"):
            ident.make_jwt(app)


def test_token_selects_installation_and_caches(app, fake):
    tok, inst = ident.get_token()
    assert (tok, inst) == (TOKEN, 77)
    assert ("POST", "/app/installations/77/access_tokens") == fake["calls"][-1][:2]
    cache = app / "agent.token"
    assert oct(cache.stat().st_mode & 0o777) == "0o600"
    n = len(fake["calls"])
    assert ident.get_token() == (TOKEN, None)
    assert len(fake["calls"]) == n


def test_refresh_near_expiry(app, fake):
    fake["expires"] = _iso(120)
    ident.get_token()
    n = len(fake["calls"])
    fake["expires"] = _iso(3600)
    ident.get_token()
    assert len(fake["calls"]) > n
    assert ident.get_token()[1] is None


def test_refuses_world_readable_cache(app, fake):
    cache = app / "agent.token"
    cache.write_text(json.dumps({"token": TOKEN, "expires_at": _iso(3600)}))
    os.chmod(cache, 0o644)
    with pytest.raises(ident.IdentityError, match="permissions") as e:
        ident.get_token()
    assert TOKEN not in str(e.value)
    assert fake["calls"] == []


def test_refuses_loose_key(app, fake):
    os.chmod(app / "agent.pem", 0o644)
    with pytest.raises(ident.IdentityError, match="agent.pem"):
        ident.get_token()


def test_no_matching_installation(app, fake):
    fake["installs"] = [{"id": 1, "account": {"login": "other"}}]
    with pytest.raises(ident.IdentityError, match="James3014"):
        ident.get_token()


def test_gh_and_git_exec(app, fake, monkeypatch):
    seen = []
    monkeypatch.setattr(os, "execvpe", lambda f, a, e: seen.append((f, a, e)))
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    assert ident.main(["gh", "--", "pr", "list"]) == 0
    f, a, e = seen[-1]
    assert (f, a) == ("gh", ["gh", "pr", "list"])
    assert e["GH_TOKEN"] == TOKEN and "GITHUB_TOKEN" not in e
    assert ident.main(["git", "--", "push", "origin", "HEAD:b"]) == 0
    f, a, e = seen[-1]
    assert (f, a) == ("git", ["git", "push", "origin", "HEAD:b"])
    basic = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
    assert e["GIT_CONFIG_COUNT"] == "3"
    assert e["GIT_CONFIG_KEY_1"] == "credential.helper" and e["GIT_CONFIG_VALUE_1"] == ""
    assert e["GIT_CONFIG_KEY_2"] == "http.https://github.com/.extraheader"
    assert e["GIT_CONFIG_VALUE_2"] == f"Authorization: basic {basic}"
    for _, argv, _ in seen:
        assert not any(TOKEN in x or basic in x for x in argv)


def test_token_prints_only_token_and_whoami_hides_it(app, fake, capsys):
    assert ident.main(["token"]) == 0
    assert capsys.readouterr().out.strip() == TOKEN
    assert ident.main(["whoami"]) == 0
    out = capsys.readouterr().out
    assert "nexus-agent-james3014" in out and "installation=77" in out and TOKEN not in out


def test_http_error_message_has_no_secrets(app, monkeypatch, capsys):
    import io
    import urllib.error
    import urllib.request

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(
            req.full_url, 401, "x", {}, io.BytesIO(b'{"message":"Bad credentials"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(ident.sys, "argv", ["x", "token"])
    assert ident.run() == 1
    err = capsys.readouterr().err
    assert "401" in err and "Bad credentials" in err
    assert "eyJ" not in err and "BEGIN" not in err
