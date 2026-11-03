from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass

SECRET_ENV = "NEXUS_V2_RUNNER_SIGNING_SECRET"
SECRET_FILE_ENV = "NEXUS_V2_RUNNER_SIGNING_SECRET_FILE"
# Built-in values that live in source: anyone with the source can sign with them, so a
# signature made with one never earns promotion credit.
NONPRODUCTION_DEFAULT_SECRETS = frozenset({
    "local-nonproduction-v2-sandbox-probe",
    "local-nonproduction-v2-physical-runner",
    "local-nonproduction-v2-skill-evidence",
})


class SigningSecretError(RuntimeError):
    pass


@dataclass(frozen=True)
class SigningSecret:
    value: str
    source: str  # "file" | "env" | "nonproduction_default"

    @property
    def nonproduction(self) -> bool:
        return self.source == "nonproduction_default" or self.value in NONPRODUCTION_DEFAULT_SECRETS

    def __repr__(self) -> str:  # never print the value
        return f"SigningSecret(source={self.source!r})"


def read_secret_file(path: str) -> str:
    """Read a secret from a file only its owner can read; refuse symlinks and loose modes."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise SigningSecretError(
            f"signing secret file cannot be opened without following symlinks: {exc.strerror}"
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SigningSecretError("signing secret file is not a regular file")
        if info.st_uid != os.geteuid():
            raise SigningSecretError("signing secret file is not owned by the current user")
        if stat.S_IMODE(info.st_mode) & 0o177:
            raise SigningSecretError(
                "signing secret file mode must be 0600 (owner read/write only)"
            )
        value = os.read(fd, 65536).decode("utf-8").strip()
    finally:
        os.close(fd)
    if not value:
        raise SigningSecretError("signing secret file is empty")
    return value


def resolve_signing_secret(
    *,
    secret_file: str | None = None,
    allow_nonproduction: bool = False,
    nonproduction_default: str,
    environ: Mapping[str, str] | None = None,
) -> SigningSecret:
    """File (observer-only) first, then the environment; the source default is used only
    when the caller passes an explicit non-production opt-in, and is marked as such."""
    env = os.environ if environ is None else environ
    path = secret_file or env.get(SECRET_FILE_ENV)
    if path:
        return SigningSecret(read_secret_file(path), "file")
    value = env.get(SECRET_ENV)
    if value:
        # The environment is readable by same-user child processes: weaker than the file.
        return SigningSecret(value, "env")
    if allow_nonproduction:
        return SigningSecret(nonproduction_default, "nonproduction_default")
    raise SigningSecretError(
        f"no signing secret: set {SECRET_FILE_ENV} (0600 file) or {SECRET_ENV}, "
        "or pass --allow-nonproduction-secret for a non-production run"
    )
