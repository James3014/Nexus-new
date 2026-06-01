import pytest
from pathlib import Path
from nexus.services.local_heal.localizer import Localizer

def test_rank_files_returns_max_3_files(tmp_path):
    # 建立一個 mock repository
    (tmp_path / "foo.py").write_text("def my_func():\n    return 'hello'", encoding="utf-8")
    (tmp_path / "bar.py").write_text("def my_other_func():\n    return 'world'", encoding="utf-8")
    (tmp_path / "baz.py").write_text("class MyClass:\n    pass", encoding="utf-8")
    (tmp_path / "qux.py").write_text("def unrelated():\n    pass", encoding="utf-8")

    localizer = Localizer()
    ranked = localizer.rank_files("my_func class MyClass", tmp_path, max_files=2)

    # 應該只回傳 2 個檔案，且核心檔案 (foo.py 與 baz.py) 應該在其中
    assert len(ranked) == 2
    paths = [doc["path"] for _, doc in ranked]
    assert "foo.py" in paths
    assert "baz.py" in paths
    assert "qux.py" not in paths


def test_extract_relevant_code_formats_correctly(tmp_path):
    file_path = tmp_path / "large.py"
    # 超過 6000 字元
    content = "def test():\n" + "    print('hello')\n" * 500
    file_path.write_text(content, encoding="utf-8")

    localizer = Localizer()
    scored_files = [(100.0, {
        "path": "large.py",
        "content": content,
        "file_path": file_path
    })]

    extracted = localizer.extract_relevant_code(scored_files)

    assert len(extracted) == 1
    path, formatted_content = extracted[0]
    assert path == "large.py"
    assert "... [truncated]" in formatted_content
    assert len(formatted_content) <= 6100


def test_extract_relevant_code_uses_query_for_symbol_level_refinement(tmp_path):
    file_path = tmp_path / "timeseries.py"
    unrelated = "\n".join(
        f"def unrelated_{i}():\n    return {i}\n"
        for i in range(220)
    )
    target = (
        "class TimeSeries:\n"
        "    def remove_column(self, name):\n"
        "        if name in self._required_columns:\n"
        "            raise ValueError(name)\n"
    )
    content = unrelated + "\n" + target
    file_path.write_text(content, encoding="utf-8")

    localizer = Localizer()
    extracted = localizer.extract_relevant_code(
        [(
            100.0,
            {
                "path": "timeseries.py",
                "content": content,
                "file_path": file_path,
            },
        )],
        query="TimeSeries remove_column _required_columns",
    )

    _, refined = extracted[0]
    assert "remove_column" in refined
    assert "_required_columns" in refined
    assert "unrelated_0" not in refined


def test_rank_files_ignores_absolute_paths_outside_repo(tmp_path):
    (tmp_path / "target.py").write_text("def target_symbol():\n    return True\n", encoding="utf-8")
    outside_path = "/private/tmp/other_repo/noisy.py"

    localizer = Localizer()
    ranked = localizer.rank_files(
        f"target_symbol stack trace {outside_path}",
        tmp_path,
        max_files=1,
    )

    assert ranked[0][1]["path"] == "target.py"


def test_rank_files_converts_absolute_paths_inside_repo_to_relative(tmp_path):
    target = tmp_path / "pkg" / "target.py"
    target.parent.mkdir()
    target.write_text("def target_symbol():\n    return True\n", encoding="utf-8")

    localizer = Localizer()
    ranked = localizer.rank_files(str(target), tmp_path, max_files=1)

    assert ranked[0][1]["path"] == "pkg/target.py"


def test_rank_files_prioritizes_ast_symbol_matches(tmp_path):
    (tmp_path / "example.py").write_text(
        "TimeSeries remove_column _required_columns\n" * 30,
        encoding="utf-8",
    )
    (tmp_path / "core.py").write_text(
        "class TimeSeries:\n"
        "    _required_columns = ['time']\n"
        "    def remove_column(self, name):\n"
        "        return name\n",
        encoding="utf-8",
    )

    localizer = Localizer()
    ranked = localizer.rank_files(
        "TimeSeries remove_column _required_columns",
        tmp_path,
        max_files=2,
        search_symbols=["TimeSeries", "remove_column", "_required_columns"],
    )

    assert ranked[0][1]["path"] == "core.py"
