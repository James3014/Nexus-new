#!/usr/bin/env python3
"""Act on GitHub as the Nexus agent GitHub App instead of the Owner account.

Usage: python3 -I scripts/ops/nexus_agent_identity.py token|whoami|gh -- ARGS|git -- ARGS
Stdlib only. The App private key is only ever read by the root-owned openssl.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
OWNER_LOGIN = "James3014"
OPENSSL = "/usr/bin/openssl"
OPENSSL_ENFORCE_OWNER = True
REFRESH_MARGIN = 300
TIMEOUT = 30


class IdentityError(Exception):
    """One-line failure reason; must never carry token/JWT/key material."""


def cred_dir() -> Path:
    override = os.environ.get("NEXUS_AGENT_APP_DIR")
    return Path(override) if override else Path.home() / ".config" / "nexus-apps"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def check_openssl(path: str | None = None) -> str:
    path = path or OPENSSL
    try:
        st = os.stat(path)
    except OSError:
        raise IdentityError(f"openssl not found at {path}") from None
    if not stat.S_ISREG(st.st_mode) or not os.access(path, os.X_OK):
        raise IdentityError(f"{path} is not an executable file")
    if OPENSSL_ENFORCE_OWNER and st.st_uid != 0:
        raise IdentityError(f"{path} is not root-owned")
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise IdentityError(f"{path} is group/other-writable")
    return path


def _check_private_file(path: Path, what: str) -> None:
    try:
        st = os.stat(path)
    except OSError:
        raise IdentityError(f"{what} missing: {path}") from None
    if st.st_uid != os.getuid():
        raise IdentityError(f"{what} is not owned by the current user")
    if st.st_mode & 0o077:
        raise IdentityError(f"{what} has group/other permissions (need 0600)")


def make_jwt(app_dir: Path, *, now: int | None = None, openssl: str | None = None) -> str:
    cfg = app_dir / "agent.json"
    pem = app_dir / "agent.pem"
    _check_private_file(cfg, "agent.json")
    _check_private_file(pem, "agent.pem")
    try:
        app_id = json.loads(cfg.read_text())["id"]
    except (OSError, ValueError, KeyError, TypeError):
        raise IdentityError("agent.json unreadable or has no id") from None
    now = int(time.time()) if now is None else now
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64(
        json.dumps(
            {"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, separators=(",", ":")
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode()
    binary = check_openssl(openssl)
    try:
        proc = subprocess.run(
            [binary, "dgst", "-sha256", "-sign", str(pem)],
            input=signing_input,
            capture_output=True,
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise IdentityError("openssl signing failed to run") from None
    if proc.returncode != 0 or not proc.stdout:
        raise IdentityError("openssl signing failed")
    return f"{header}.{claims}.{_b64(proc.stdout)}"


def http(method: str, path: str, bearer: str) -> dict:
    req = urllib.request.Request(
        API + path,
        method=method,
        data=b"" if method == "POST" else None,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nexus-agent-identity",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        msg = ""
        try:
            msg = str(json.loads(exc.read().decode()).get("message", ""))
        except Exception:
            pass
        raise IdentityError(f"GitHub HTTP {exc.code}: {msg[:200]}") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise IdentityError(f"GitHub request failed: {method} {path}") from None


def find_installation(jwt: str) -> int:
    data = http("GET", f"/users/{OWNER_LOGIN}/installation", jwt)
    inst = data.get("id") if isinstance(data, dict) else None
    if not isinstance(inst, int) or isinstance(inst, bool):
        raise IdentityError(f"no installation for account {OWNER_LOGIN}")
    return inst


def _parse_expiry(value: str) -> float:
    from datetime import datetime, timezone

    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def _check_dir(path: Path) -> None:
    try:
        st = os.stat(path)
    except OSError:
        raise IdentityError(f"credentials dir missing: {path}") from None
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise IdentityError("credentials dir not user-owned or has group/other permissions")


def _read_cache(path: Path, app_id: str) -> dict | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError:
        raise IdentityError("token cache cannot be opened safely (symlink?)") from None
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise IdentityError("token cache not owned by user or has group/other permissions")
        try:
            data = json.loads(fh.read().decode())
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    inst = data.get("installation_id")
    if (
        not isinstance(data.get("token"), str)
        or not isinstance(data.get("expires_at"), str)
        or data.get("app_id") != app_id
        or not isinstance(inst, int)
        or isinstance(inst, bool)
    ):
        return None
    return data


def _write_cache(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _app_id(app_dir: Path) -> str:
    cfg = app_dir / "agent.json"
    _check_private_file(cfg, "agent.json")
    try:
        return str(json.loads(cfg.read_text())["id"])
    except (OSError, ValueError, KeyError, TypeError):
        raise IdentityError("agent.json unreadable or has no id") from None


def get_token(*, now: float | None = None, openssl: str | None = None) -> tuple[str, int | None]:
    """Return (token, installation_id or None when served from cache)."""
    app_dir = cred_dir()
    _check_dir(app_dir)
    cache = app_dir / "agent.token"
    now = time.time() if now is None else now
    app_id = _app_id(app_dir)
    cached = _read_cache(cache, app_id)
    if cached:
        try:
            if _parse_expiry(cached["expires_at"]) - now > REFRESH_MARGIN:
                return cached["token"], None
        except ValueError:
            pass
    jwt = make_jwt(app_dir, now=int(now), openssl=openssl)
    inst = find_installation(jwt)
    resp = http("POST", f"/app/installations/{inst}/access_tokens", jwt)
    token, exp = resp.get("token"), resp.get("expires_at")
    if not isinstance(token, str) or not isinstance(exp, str):
        raise IdentityError("access token response malformed")
    _write_cache(
        cache, {"token": token, "expires_at": exp, "app_id": app_id, "installation_id": inst}
    )
    return token, inst


def cmd_whoami() -> int:
    token, inst = get_token()
    app_dir = cred_dir()
    jwt = make_jwt(app_dir)
    slug = http("GET", "/app", jwt).get("slug", "?")
    if inst is None:
        inst = find_installation(jwt)
    count = http("GET", "/installation/repositories", token).get("total_count", "?")
    print(f"app={slug} installation={inst} repositories={count}")
    return 0


def git_env(token: str, base: dict | None = None) -> dict:
    env = dict(os.environ if base is None else base)
    try:
        n = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        n = 0
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    header_key = "http.https://github.com/.extraheader"
    pairs = [
        ("credential.helper", ""),
        ("protocol.ssh.allow", "never"),
        (header_key, ""),  # list reset: drop any inherited extraheader
        (header_key, f"Authorization: basic {basic}"),
    ]
    for i, (k, v) in enumerate(pairs, start=n):
        env[f"GIT_CONFIG_KEY_{i}"] = k
        env[f"GIT_CONFIG_VALUE_{i}"] = v
    env["GIT_CONFIG_COUNT"] = str(n + len(pairs))
    env["GIT_TERMINAL_PROMPT"] = "0"
    for k in ("GIT_ASKPASS", "SSH_ASKPASS", "GITHUB_TOKEN", "GH_TOKEN"):
        env.pop(k, None)
    return env


def gh_env(token: str, base: dict | None = None) -> dict:
    env = git_env(token, base)
    for k in ("GITHUB_TOKEN", "GH_HOST", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        env.pop(k, None)
    env["GH_TOKEN"] = token
    return env


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"token", "whoami", "gh", "git"}:
        raise IdentityError("usage: token | whoami | gh -- ARGS | git -- ARGS")
    cmd, rest = argv[0], argv[1:]
    if cmd in {"token", "whoami"}:
        if rest:
            raise IdentityError(f"{cmd} takes no arguments")
        if cmd == "whoami":
            return cmd_whoami()
        print(get_token()[0])
        return 0
    if rest[:1] == ["--"]:
        rest = rest[1:]
    token, _ = get_token()
    exe = shutil.which(cmd)
    if not exe:
        raise IdentityError(f"{cmd} not found on PATH")
    env = gh_env(token) if cmd == "gh" else git_env(token)
    os.execvpe(exe, [exe, *rest], env)
    return 0


def run() -> int:
    try:
        return main(sys.argv[1:])
    except IdentityError as exc:
        print(f"nexus_agent_identity: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"nexus_agent_identity: unexpected {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
