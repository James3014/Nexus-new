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
        "install": {"id": 77},
        "expires": _iso(3600),
    }

    def http(method, path, bearer):
        state["calls"].append((method, path, bearer))
        if path == "/users/James3014/installation":
            if state["install"] is None:
                raise ident.IdentityError("GitHub HTTP 404: Not Found")
            return state["install"]
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


def test_openssl_ownership_enforced_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(ident, "OPENSSL_ENFORCE_OWNER", True)
    f = tmp_path / "openssl"
    shutil.copy(OPENSSL, f)
    f.chmod(0o755)
    if os.getuid() != 0:
        with pytest.raises(ident.IdentityError, match="root-owned"):
            ident.check_openssl(str(f))  # explicit path does not disable the check
    monkeypatch.setattr(ident, "OPENSSL_ENFORCE_OWNER", False)
    f.chmod(0o775)
    with pytest.raises(ident.IdentityError, match="writable"):
        ident.check_openssl(str(f))
    with pytest.raises(ident.IdentityError, match="not found"):
        ident.check_openssl(str(tmp_path / "nope"))


def test_make_jwt_enforces_owner_by_default(app, monkeypatch, tmp_path):
    monkeypatch.setattr(ident, "OPENSSL_ENFORCE_OWNER", True)
    mine = tmp_path / "openssl"
    shutil.copy(OPENSSL, mine)
    mine.chmod(0o755)
    if os.getuid() != 0:
        with pytest.raises(ident.IdentityError, match="root-owned"):
            ident.make_jwt(app, openssl=str(mine))


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
    fake["install"] = None
    with pytest.raises(ident.IdentityError, match="404"):
        ident.get_token()


def test_gh_and_git_exec(app, fake, monkeypatch):
    seen = []
    monkeypatch.setattr(os, "execvpe", lambda f, a, e: seen.append((f, a, e)))
    monkeypatch.setattr(ident.shutil, "which", lambda c: f"/abs/{c}")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    assert ident.main(["gh", "--", "pr", "list"]) == 0
    f, a, e = seen[-1]
    assert (f, a) == ("/abs/gh", ["/abs/gh", "pr", "list"])
    assert e["GH_TOKEN"] == TOKEN and "GITHUB_TOKEN" not in e
    assert ident.main(["git", "--", "push", "origin", "HEAD:b"]) == 0
    f, a, e = seen[-1]
    assert (f, a) == ("/abs/git", ["/abs/git", "push", "origin", "HEAD:b"])
    basic = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
    assert e["GIT_CONFIG_COUNT"] == "5"
    assert e["GIT_CONFIG_KEY_1"] == "credential.helper" and e["GIT_CONFIG_VALUE_1"] == ""
    assert (e["GIT_CONFIG_KEY_2"], e["GIT_CONFIG_VALUE_2"]) == ("protocol.ssh.allow", "never")
    assert e["GIT_CONFIG_KEY_3"] == "http.https://github.com/.extraheader"
    assert e["GIT_CONFIG_VALUE_3"] == ""
    assert e["GIT_CONFIG_KEY_4"] == "http.https://github.com/.extraheader"
    assert e["GIT_CONFIG_VALUE_4"] == f"Authorization: basic {basic}"
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


def _urlmatch(env, url, tmp_path):
    env = {k: v for k, v in env.items() if not k.startswith("GIT_CONFIG_GLOBAL")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", HOME=str(tmp_path))
    out = subprocess.run(
        ["git", "config", "--get-urlmatch", "http.extraheader", url],
        env=env,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip().splitlines()


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_real_git_extraheader_urlmatch(tmp_path):
    fake_tok = "ghs_" + "F" * 36
    basic = base64.b64encode(f"x-access-token:{fake_tok}".encode()).decode()
    env = ident.git_env(fake_tok, {"PATH": os.environ["PATH"]})
    assert _urlmatch(env, "https://github.com/x", tmp_path) == [f"Authorization: basic {basic}"]
    assert _urlmatch(env, "https://example.com/x", tmp_path) == []
    # inherited header is reset, not doubled
    pre = {
        "PATH": os.environ["PATH"],
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": "Authorization: basic OLD",
    }
    env = ident.git_env(fake_tok, pre)
    assert _urlmatch(env, "https://github.com/x", tmp_path) == [f"Authorization: basic {basic}"]
    # --get-urlmatch shows only the last value, so also check that an empty
    # reset entry for the same key comes right before the real header.
    pairs = [
        (env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"])
        for i in range(int(env["GIT_CONFIG_COUNT"]))
    ]
    key = "http.https://github.com/.extraheader"
    real = pairs.index((key, f"Authorization: basic {basic}"))
    assert real > 1 and pairs[real - 1] == (key, "")
    assert pairs[0] == (key, "Authorization: basic OLD")


def test_env_hardening_and_gh_includes_git_pairs():
    base = {
        "GIT_ASKPASS": "a",
        "SSH_ASKPASS": "b",
        "GH_HOST": "h",
        "GITHUB_TOKEN": "t",
        "GH_ENTERPRISE_TOKEN": "e",
        "GITHUB_ENTERPRISE_TOKEN": "e",
    }
    g = ident.git_env("tok", base)
    assert g["GIT_TERMINAL_PROMPT"] == "0"
    assert "GIT_ASKPASS" not in g and "SSH_ASKPASS" not in g
    pairs = {(g[f"GIT_CONFIG_KEY_{i}"], g[f"GIT_CONFIG_VALUE_{i}"]) for i in range(4)}
    assert ("protocol.ssh.allow", "never") in pairs
    h = ident.gh_env("tok", base)
    assert h["GH_TOKEN"] == "tok"
    for k in ("GH_HOST", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        assert k not in h
    assert all(
        h[f"GIT_CONFIG_{x}_{i}"] == g[f"GIT_CONFIG_{x}_{i}"]
        for i in range(4)
        for x in ("KEY", "VALUE")
    )


def test_symlinked_cache_refused(app, fake, tmp_path):
    real = tmp_path / "real"
    real.write_text(json.dumps({"token": TOKEN}))
    os.chmod(real, 0o600)
    (app / "agent.token").symlink_to(real)
    with pytest.raises(ident.IdentityError, match="cache"):
        ident.get_token()


def test_loose_credentials_dir_refused(app, fake):
    os.chmod(app, 0o755)
    with pytest.raises(ident.IdentityError, match="dir"):
        ident.get_token()


def test_cache_mismatch_refetches(app, fake):
    cache = app / "agent.token"
    good = {"token": TOKEN, "expires_at": _iso(3600), "app_id": "4242", "installation_id": 77}
    for bad in ({"app_id": "999"}, {"installation_id": "77"}, {"installation_id": None}):
        cache.write_text(json.dumps({**good, **bad}))
        os.chmod(cache, 0o600)
        n = len(fake["calls"])
        assert ident.get_token() == (TOKEN, 77)
        assert len(fake["calls"]) > n
    cache.write_text(json.dumps(good))
    os.chmod(cache, 0o600)
    assert ident.get_token() == (TOKEN, None)


def test_unexpected_exception_prints_type_only(app, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError(TOKEN)

    monkeypatch.setattr(ident, "get_token", boom)
    monkeypatch.setattr(ident.sys, "argv", ["x", "token"])
    assert ident.run() == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err and TOKEN not in err
