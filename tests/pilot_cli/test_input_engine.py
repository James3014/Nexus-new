import io
import inspect
import os

import nexus.pilot_cli.input_engine as input_engine
import pytest

try:
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput
except Exception:  # pragma: no cover
    create_pipe_input = None
    DummyOutput = None
from nexus.pilot_cli.input_engine import BRACKETED_PASTE_END
from nexus.pilot_cli.input_engine import BRACKETED_PASTE_START
from nexus.pilot_cli.input_engine import _build_prompt_toolkit_session
from nexus.pilot_cli.input_engine import _should_use_prompt_toolkit
from nexus.pilot_cli.input_engine import collect_cbreak_line
from nexus.pilot_cli.input_engine import collect_cbreak_text
from nexus.pilot_cli.input_engine import read_interactive_line


def test_collect_cbreak_line_reads_until_newline():
    writes = []
    data = [b"h", b"i", b"\n"]

    result = collect_cbreak_line(
        read_byte_fn=lambda: data.pop(0),
        write_fn=writes.append,
    )

    assert result == "hi"
    assert writes[-1] == "\n"


def test_collect_cbreak_line_handles_backspace():
    writes = []
    data = [b"a", b"b", b"\x7f", b"c", b"\n"]

    result = collect_cbreak_line(
        read_byte_fn=lambda: data.pop(0),
        write_fn=writes.append,
    )

    assert result == "ac"
    assert "\b \b" in writes


def test_collect_cbreak_line_handles_utf8_text():
    writes = []
    encoded = list("哈囉".encode("utf-8"))
    data = [bytes([value]) for value in encoded] + [b"\n"]

    result = collect_cbreak_line(
        read_byte_fn=lambda: data.pop(0),
        write_fn=writes.append,
    )

    assert result == "哈囉"


def test_collect_cbreak_line_ctrl_d_raises_eof_on_empty_line():
    try:
        collect_cbreak_line(
            read_byte_fn=lambda: b"\x04",
            write_fn=lambda text: None,
        )
    except EOFError:
        return
    assert False, "expected EOFError"


def test_collect_cbreak_text_coalesces_pasted_multiline_block():
    writes = []
    first = "第一".encode("utf-8")
    second = "第二".encode("utf-8")
    chunks = [bytes([value]) for value in first] + [b"\n"] + [bytes([value]) for value in second] + [b"\n"]
    pending = iter([True, False])

    result = collect_cbreak_text(
        read_byte_fn=lambda: chunks.pop(0),
        write_fn=writes.append,
        has_pending_input_fn=lambda: next(pending),
    )

    assert result == "第一\n第二"


def test_collect_cbreak_text_flushes_multiline_paste_on_idle_without_final_newline():
    writes = []
    first = "第一".encode("utf-8")
    second = "第二".encode("utf-8")
    chunks = [bytes([value]) for value in first] + [b"\n"] + [bytes([value]) for value in second] + [None]
    pending = iter([True, False])

    result = collect_cbreak_text(
        read_byte_fn=lambda: chunks.pop(0),
        write_fn=writes.append,
        has_pending_input_fn=lambda: next(pending),
    )

    assert result == "第一\n第二"


def test_collect_cbreak_text_keeps_waiting_for_single_line_without_newline():
    writes = []
    chunks = [b"a", None, b"b", b"\n"]

    result = collect_cbreak_text(
        read_byte_fn=lambda: chunks.pop(0),
        write_fn=writes.append,
        has_pending_input_fn=lambda: False,
    )

    assert result == "ab"


def test_collect_cbreak_text_flushes_after_multiple_newlines_and_idle():
    writes = []
    text = "第一段\n第二段\n第三段".encode("utf-8")
    chunks = [bytes([value]) for value in text] + [None]
    pending = iter([True, True, False])

    result = collect_cbreak_text(
        read_byte_fn=lambda: chunks.pop(0),
        write_fn=writes.append,
        has_pending_input_fn=lambda: next(pending),
    )

    assert result == "第一段\n第二段\n第三段"


def test_collect_cbreak_text_ignores_bracketed_paste_markers():
    writes = []
    body = "第一行\n第二行".encode("utf-8")
    stream = [bytes([value]) for value in BRACKETED_PASTE_START + body + BRACKETED_PASTE_END]
    pending = iter([True, False])

    result = collect_cbreak_text(
        read_byte_fn=lambda: stream.pop(0),
        write_fn=writes.append,
        has_pending_input_fn=lambda: next(pending),
    )

    assert result == "第一行\n第二行"


def test_should_use_prompt_toolkit_by_default(monkeypatch):
    monkeypatch.delenv("NEXUS_PILOT_INPUT_BACKEND", raising=False)

    assert _should_use_prompt_toolkit() is True


def test_should_use_prompt_toolkit_can_be_disabled(monkeypatch):
    monkeypatch.setenv("NEXUS_PILOT_INPUT_BACKEND", "cbreak")

    assert _should_use_prompt_toolkit() is False


def test_build_prompt_toolkit_session_enables_multiline_submit(monkeypatch):
    source = inspect.getsource(_build_prompt_toolkit_session)

    assert '@bindings.add("escape")' in source
    assert '"multiline": False' in source


def test_prompt_toolkit_session_accepts_bracketed_paste_as_single_message():
    if create_pipe_input is None or DummyOutput is None:
        pytest.skip("prompt_toolkit not installed in test environment")

    with create_pipe_input() as pipe_input:
        session = _build_prompt_toolkit_session(input=pipe_input, output=DummyOutput())
        assert session is not None
        result_holder = {}

        def run_prompt():
            result_holder["result"] = session.prompt("NEXUS > ")

        import threading
        import time

        thread = threading.Thread(target=run_prompt)
        thread.start()
        time.sleep(0.1)
        pipe_input.send_text("\x1b[200~第一行\n第二行\x1b[201~")
        time.sleep(0.1)
        pipe_input.send_text("\r")
        thread.join(timeout=2)

        assert result_holder["result"] == "第一行\n第二行"


def test_read_interactive_line_prefers_prompt_toolkit_when_available(monkeypatch):
    class FakeSession:
        def prompt(self, prompt):
            assert prompt == "NEXUS > "
            return "pasted long question"

    class FakeInput(io.StringIO):
        def isatty(self):
            return True

        def fileno(self):
            return 0

    monkeypatch.setattr(input_engine, "_should_use_prompt_toolkit", lambda: True)
    monkeypatch.setattr(
        input_engine,
        "_get_prompt_toolkit_session",
        lambda input_stream=None, output_stream=None: FakeSession(),
    )

    result = read_interactive_line(
        "NEXUS > ",
        input_stream=FakeInput(),
        output_stream=io.StringIO(),
    )

    assert result == "pasted long question"


def test_read_interactive_line_requires_prompt_toolkit_for_default_backend(monkeypatch):
    class FakeInput(io.StringIO):
        def isatty(self):
            return True

        def fileno(self):
            return 0

    monkeypatch.setattr(input_engine, "_should_use_prompt_toolkit", lambda: True)
    monkeypatch.setattr(
        input_engine,
        "_get_prompt_toolkit_session",
        lambda input_stream=None, output_stream=None: None,
    )

    try:
        read_interactive_line(
            "NEXUS > ",
            input_stream=FakeInput(),
            output_stream=io.StringIO(),
        )
    except RuntimeError as exc:
        assert "prompt_toolkit is required" in str(exc)
        return

    assert False, "expected RuntimeError when prompt_toolkit backend is unavailable"


def test_read_interactive_line_uses_cbreak_when_prompt_toolkit_disabled(monkeypatch):
    class FakeInput(io.StringIO):
        def isatty(self):
            return True

        def fileno(self):
            return 0

    monkeypatch.setattr(input_engine, "_should_use_prompt_toolkit", lambda: False)
    monkeypatch.setattr(input_engine, "_get_prompt_toolkit_session", lambda **kwargs: None)
    monkeypatch.setattr(input_engine, "collect_cbreak_text", lambda **kwargs: "legacy cbreak")

    class FakeTermios:
        ICANON = 1
        ECHO = 2
        TCSADRAIN = 0
        VMIN = 5
        VTIME = 6

        @staticmethod
        def tcgetattr(fd):
            return [0, 0, 0, 7, 0, 0, [0, 0, 0, 0, 0, 0, 0]]

        @staticmethod
        def tcsetattr(fd, when, settings):
            return None

    monkeypatch.setitem(os.sys.modules, "termios", FakeTermios)
    monkeypatch.setattr(input_engine.select, "select", lambda *args, **kwargs: ([0], [], []))
    monkeypatch.setattr(input_engine.os, "read", lambda fd, size: b"\n")

    result = read_interactive_line(
        "NEXUS > ",
        input_stream=FakeInput(),
        output_stream=io.StringIO(),
    )

    assert result == "legacy cbreak"
