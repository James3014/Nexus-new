"""Pure, pre-materialized GitHub pull-request compatibility adapter."""

import re
from dataclasses import dataclass

from product.evidence import ChangeSet
from product.kernel import CertificationInput, certify

_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FIELDS = frozenset(
    {
        "repository_owner",
        "repository_name",
        "pr_number",
        "base_sha",
        "head_sha",
        "diff_hash",
        "changed_paths",
    }
)


def _text(value, field):
    if type(value) is not str or not value or value != value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be a normalized nonblank string")


@dataclass(frozen=True)
class GitHubPullRequestSnapshot:
    repository_owner: str
    repository_name: str
    pr_number: int
    base_sha: str
    head_sha: str
    diff_hash: str
    changed_paths: tuple[str, ...]

    def __post_init__(self):
        _text(self.repository_owner, "repository_owner")
        _text(self.repository_name, "repository_name")
        if type(self.pr_number) is not int or self.pr_number <= 0:
            raise ValueError("pr_number must be a positive exact int")
        for field in ("base_sha", "head_sha"):
            value = getattr(self, field)
            if type(value) is not str or _SHA40.fullmatch(value) is None:
                raise ValueError(f"{field} must be lowercase 40-hex SHA")
        if self.base_sha == self.head_sha:
            raise ValueError("base_sha and head_sha must differ")
        if type(self.diff_hash) is not str or _SHA256.fullmatch(self.diff_hash) is None:
            raise ValueError("diff_hash must be sha256:<64 lowercase hex>")
        if type(self.changed_paths) is not tuple or not self.changed_paths:
            raise ValueError("changed_paths must be a non-empty tuple")
        if len(self.changed_paths) != len(set(self.changed_paths)):
            raise ValueError("changed_paths must be unique")
        for path in self.changed_paths:
            _text(path, "changed_paths")
            if (
                path.startswith("/")
                or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                raise ValueError("changed_paths must contain normalized relative paths")

    def to_dict(self):
        return {
            "repository_owner": self.repository_owner,
            "repository_name": self.repository_name,
            "pr_number": self.pr_number,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "diff_hash": self.diff_hash,
            "changed_paths": list(self.changed_paths),
        }


def snapshot_to_dict(snapshot):
    if type(snapshot) is not GitHubPullRequestSnapshot:
        raise TypeError("snapshot must be GitHubPullRequestSnapshot")
    return snapshot.to_dict()


def load_snapshot(payload):
    if type(payload) is not dict or set(payload) != _FIELDS:
        raise ValueError("malformed GitHub pull-request snapshot keys")
    values = dict(payload)
    if type(values["changed_paths"]) is not list:
        raise TypeError("changed_paths must be a list in serialized snapshots")
    values["changed_paths"] = tuple(values["changed_paths"])
    return GitHubPullRequestSnapshot(**values)


load_github_pull_request_snapshot = load_snapshot
serialize_github_pull_request_snapshot = snapshot_to_dict


def to_changeset(snapshot):
    if type(snapshot) is not GitHubPullRequestSnapshot:
        raise TypeError("snapshot must be GitHubPullRequestSnapshot")
    change_set_id = (
        f"github:{snapshot.repository_owner}/{snapshot.repository_name}"
        f"#pr-{snapshot.pr_number}@{snapshot.head_sha}"
    )
    return ChangeSet(
        change_set_id,
        snapshot.base_sha,
        snapshot.head_sha,
        snapshot.diff_hash,
        snapshot.changed_paths,
    )


github_snapshot_to_changeset = to_changeset


def certify_pull_request(
    snapshot,
    contract,
    plan,
    evidence,
    *,
    policy_accepted=None,
    authority_present=None,
    approval_present=None,
    signing_present=None,
):
    change_set = to_changeset(snapshot)
    return certify(
        CertificationInput(
            contract,
            change_set,
            plan,
            evidence,
            policy_accepted,
            authority_present,
            approval_present,
            signing_present,
        )
    )


__all__ = [
    "GitHubPullRequestSnapshot",
    "certify_pull_request",
    "github_snapshot_to_changeset",
    "load_github_pull_request_snapshot",
    "serialize_github_pull_request_snapshot",
    "snapshot_to_dict",
    "to_changeset",
]
