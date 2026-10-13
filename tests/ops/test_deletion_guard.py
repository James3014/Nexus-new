from __future__ import annotations

import urllib.error

from scripts.ops import deletion_guard as dg

TOKEN = "tok" + "en-" + "S" * 20


def _fake(files, labels, calls=None):
    def fetch(url, token):
        if calls is not None:
            calls.append(url)
        assert token == TOKEN
        if "/pulls/" in url:
            page = int(url.rsplit("page=", 1)[1])
            return files[(page - 1) * 100 : page * 100]
        page = int(url.rsplit("page=", 1)[1])
        return labels[(page - 1) * 100 : page * 100]

    return fetch


def _f(name, status="modified", prev=None):
    entry = {"filename": name, "status": status}
    if prev:
        entry["previous_filename"] = prev
    return entry


def test_no_deletions_passes(capsys):
    assert dg.run("o/r", 1, TOKEN, _fake([_f("a.py"), _f("b.py", "added")], [])) == 0
    assert "no deletions" in capsys.readouterr().out


def test_deletion_without_label_fails_and_lists_path(capsys):
    rc = dg.run("o/r", 1, TOKEN, _fake([_f("gone.py", "removed")], [{"name": "bug"}]))
    out = capsys.readouterr().out
    assert rc == 1
    assert "gone.py" in out
    assert "owner-approved-deletion" in out


def test_deletion_with_label_passes():
    labels = [{"name": "bug"}, {"name": "owner-approved-deletion"}]
    assert dg.run("o/r", 1, TOKEN, _fake([_f("gone.py", "removed")], labels)) == 0


def test_rename_counts_as_deletion(capsys):
    rc = dg.run("o/r", 1, TOKEN, _fake([_f("new.py", "renamed", "old.py")], []))
    out = capsys.readouterr().out
    assert rc == 1
    assert "old.py" in out and "new.py" in out


def test_pagination_finds_deletion_on_second_page():
    files = [_f(f"f{i}.py") for i in range(100)] + [_f("late.py", "removed")]
    calls: list[str] = []
    assert dg.run("o/r", 1, TOKEN, _fake(files, [], calls)) == 1
    assert any("page=2" in c and "per_page=100" in c for c in calls)


def test_file_cap_fails_closed(capsys):
    files = [_f(f"f{i}.py") for i in range(3000)]
    assert dg.run("o/r", 1, TOKEN, _fake(files, [])) == 1
    assert "cap" in capsys.readouterr().out


def test_api_error_fails_closed_one_line(capsys):
    def boom(url, token):
        raise urllib.error.URLError("down " + token)

    assert dg.run("o/r", 1, TOKEN, boom) == 1
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1
    assert "FAIL" in out


def test_token_never_printed(capsys):
    dg.run("o/r", 1, TOKEN, _fake([_f("gone.py", "removed")], []))

    def boom(url, token):
        raise urllib.error.URLError(token)

    dg.run("o/r", 1, TOKEN, boom)
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err


def test_main_missing_token_fails_closed(monkeypatch, capsys):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert dg.main(["--repo", "o/r", "--pr", "1"]) == 1
