from __future__ import annotations

import os

import pytest

from nexus.learning.zero_trust_v2_signing_secret import (
    SECRET_ENV,
    SECRET_FILE_ENV,
    SigningSecretError,
    resolve_signing_secret,
)

DEFAULT = "local-nonproduction-v2-sandbox-probe"


def _write(tmp_path, mode: int = 0o600, text: str = "fake-secret-file-value\n"):
    path = tmp_path / "secret"
    path.write_text(text)
    path.chmod(mode)
    return str(path)


def test_no_secret_refuses_without_explicit_nonproduction_flag() -> None:
    with pytest.raises(SigningSecretError):
        resolve_signing_secret(nonproduction_default=DEFAULT, environ={})


def test_explicit_nonproduction_flag_uses_default_and_marks_it() -> None:
    secret = resolve_signing_secret(
        allow_nonproduction=True, nonproduction_default=DEFAULT, environ={}
    )
    assert secret.value == DEFAULT
    assert secret.nonproduction is True
    assert DEFAULT not in repr(secret)


def test_env_secret_still_works_but_is_tagged_env() -> None:
    secret = resolve_signing_secret(nonproduction_default=DEFAULT, environ={SECRET_ENV: "fake-env"})
    assert (secret.value, secret.source, secret.nonproduction) == ("fake-env", "env", False)


def test_owner_only_file_is_preferred_over_env(tmp_path) -> None:
    path = _write(tmp_path)
    secret = resolve_signing_secret(
        nonproduction_default=DEFAULT, environ={SECRET_ENV: "fake-env", SECRET_FILE_ENV: path}
    )
    assert (secret.value, secret.source) == ("fake-secret-file-value", "file")


def test_loose_file_mode_is_refused(tmp_path) -> None:
    with pytest.raises(SigningSecretError, match="0600"):
        resolve_signing_secret(
            secret_file=_write(tmp_path, 0o644), nonproduction_default=DEFAULT, environ={}
        )


def test_symlinked_secret_file_is_refused(tmp_path) -> None:
    real = _write(tmp_path)
    link = tmp_path / "link"
    os.symlink(real, link)
    with pytest.raises(SigningSecretError):
        resolve_signing_secret(secret_file=str(link), nonproduction_default=DEFAULT, environ={})


def test_empty_secret_file_is_refused(tmp_path) -> None:
    with pytest.raises(SigningSecretError, match="empty"):
        resolve_signing_secret(
            secret_file=_write(tmp_path, text="\n"), nonproduction_default=DEFAULT, environ={}
        )


def test_a_directory_as_secret_file_is_refused(tmp_path) -> None:
    folder = tmp_path / "secret"
    folder.mkdir(mode=0o700)

    with pytest.raises(SigningSecretError, match="not a regular file"):
        resolve_signing_secret(secret_file=str(folder), nonproduction_default=DEFAULT, environ={})


def test_a_secret_file_that_is_not_utf8_is_refused(tmp_path) -> None:
    path = tmp_path / "secret"
    path.write_bytes(b"\xff\xfe\x00")
    os.chmod(path, 0o600)

    with pytest.raises(SigningSecretError, match="not UTF-8"):
        resolve_signing_secret(secret_file=str(path), nonproduction_default=DEFAULT, environ={})
