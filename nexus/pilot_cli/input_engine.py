from typing import Any, Dict, List, Optional, Tuple
import codecs
import os
import select
import sys

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
    from nexus.pilot_cli.session import PilotSession
except Exception:  # pragma: no cover
    PromptSession = None
    KeyBindings = None
    PilotSession = None

BRACKETED_PASTE_START = b"\x1b[200~"
BRACKETED_PASTE_END = b"\x1b[201~"
_PROMPT_SESSION = None


def _build_prompt_toolkit_session(input=None, output=None):
    if PromptSession is None or KeyBindings is None:
        return None

    bindings = KeyBindings()

    @bindings.add("escape")
    def _clear(event):
        event.app.current_buffer.reset()

    kwargs = {
        "multiline": False,
        "key_bindings": bindings,
        "wrap_lines": True,
    }
    if input is not None:
        kwargs["input"] = input
    if output is not None:
        kwargs["output"] = output
    return PromptSession(**kwargs)


def _should_use_prompt_toolkit() -> bool:
    backend = os.getenv("NEXUS_PILOT_INPUT_BACKEND", "prompt_toolkit")
    return backend != "cbreak"


def _get_prompt_toolkit_session(input_stream=None, output_stream=None):
    global _PROMPT_SESSION
    if _PROMPT_SESSION is None:
        _PROMPT_SESSION = _build_prompt_toolkit_session()
    return _PROMPT_SESSION


def collect_cbreak_text(
    read_byte_fn,
    write_fn,
    has_pending_input_fn=None,
    reset_line_fn=None,
) -> str:
    """採集 cbreak 模式下的輸入，處理多行貼上與逸出序列。"""
    ctx = _CBreakContext(
        decoder=codecs.getincrementaldecoder("utf-8")(),
        has_pending_input_fn=has_pending_input_fn or (lambda: False),
        reset_line_fn=reset_line_fn or (lambda: None),
        write_fn=write_fn
    )

    while True:
        chunk = read_byte_fn()
        if chunk is None:
            if ctx.handle_timeout(): continue
            if ctx.buffer and ctx.saw_newline:
                write_fn("\n")
                return "".join(ctx.buffer)
            continue
        if not chunk:
            if ctx.buffer:
                write_fn("\n")
                return "".join(ctx.buffer)
            raise EOFError

        # 1. 處理控制字元與換行
        result = ctx.process_chunk(chunk)
        if result is not None:
            return result

class _CBreakContext:
    """維護 cbreak 輸入狀態的內部上下文。"""
    def __init__(self, decoder, has_pending_input_fn, reset_line_fn, write_fn):
        self.buffer = []
        self.decoder = decoder
        self.has_pending_input_fn = has_pending_input_fn
        self.reset_line_fn = reset_line_fn
        self.write_fn = write_fn
        self.saw_newline = False
        self.escape_buffer = bytearray()
        self.pending_escape = False

    def handle_timeout(self) -> bool:
        """處理讀取逾時。若在逸出序列中逾時則重設。"""
        if self.pending_escape:
            self._reset_state()
            self.reset_line_fn()
            return True
        return False

    def process_chunk(self, chunk: bytes) -> Optional[str]:
        """處理單個位元組區塊。"""
        if chunk in (b"\r", b"\n"):
            return self._handle_newline()
        if chunk == b"\x04": # Ctrl-D
            return self._finalize()
        if chunk in (b"\x7f", b"\b"): # Backspace
            self._handle_backspace()
            return None
        if self.escape_buffer or chunk == b"\x1b":
            return self._handle_escape(chunk)
        
        return self._handle_text(chunk)

    def _reset_state(self):
        self.buffer = []
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.saw_newline = False
        self.pending_escape = False
        self.escape_buffer.clear()

    def _handle_newline(self) -> Optional[str]:
        self.write_fn("\n")
        self.saw_newline = True
        if self.has_pending_input_fn():
            self.buffer.append("\n")
            return None
        return "".join(self.buffer)

    def _finalize(self) -> str:
        if self.buffer: self.write_fn("\n")
        else: raise EOFError
        return "".join(self.buffer)

    def _handle_backspace(self):
        if self.buffer:
            self.buffer.pop()
            self.write_fn("\b \b")

    def _handle_escape(self, chunk: bytes) -> Optional[str]:
        self.escape_buffer.extend(chunk)
        eb = bytes(self.escape_buffer)
        if eb == b"\x1b":
            self.pending_escape = True
            return None
        if eb == BRACKETED_PASTE_START:
            self.pending_escape = False
            self.escape_buffer.clear()
            return None
        if eb == BRACKETED_PASTE_END:
            self.pending_escape = False
            self.escape_buffer.clear()
            self.write_fn("\n")
            return "".join(self.buffer)
        if BRACKETED_PASTE_START.startswith(eb) or BRACKETED_PASTE_END.startswith(eb):
            return None
        if eb.startswith(b"\x1b["): # ANSI escape
            self.pending_escape = False
            self.escape_buffer.clear()
            return None
        # 未知逸出序列，視為非法並重設
        self._reset_state()
        self.reset_line_fn()
        return None

    def _handle_text(self, chunk: bytes) -> Optional[str]:
        try:
            text = self.decoder.decode(chunk)
            if text:
                self.buffer.append(text)
                self.write_fn(text)
        except UnicodeDecodeError: pass
        return None


def collect_cbreak_line(read_byte_fn, write_fn) -> str:
    return collect_cbreak_text(
        read_byte_fn=read_byte_fn,
        write_fn=write_fn,
        has_pending_input_fn=lambda: False,
    )


def can_use_cbreak_input(input_stream=None) -> bool:
    stream = input_stream or sys.stdin
    return hasattr(stream, "isatty") and stream.isatty() and hasattr(stream, "fileno")


def read_interactive_line(prompt: str, input_stream=None, output_stream=None) -> str:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout

    if not can_use_cbreak_input(input_stream):
        return input(prompt)

    if _should_use_prompt_toolkit():
        prompt_session: Optional[PromptSession] = _get_prompt_toolkit_session(
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if prompt_session is None:
            raise RuntimeError(
                "prompt_toolkit is required for interactive Nexus Pilot sessions. "
                "Reinstall with scripts/ops/install_nexus_pilot_friend.sh."
            )
        return prompt_session.prompt(prompt)

    try:
        import termios
    except Exception:
        return input(prompt)

    fd = input_stream.fileno()
    old_settings = termios.tcgetattr(fd)
    new_settings = termios.tcgetattr(fd)
    new_settings[3] = new_settings[3] & ~(termios.ICANON | termios.ECHO)
    new_settings[6][termios.VMIN] = 1
    new_settings[6][termios.VTIME] = 0

    output_stream.write(prompt)
    output_stream.flush()

    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        return collect_cbreak_text(
            read_byte_fn=lambda: os.read(fd, 1)
            if select.select([fd], [], [], 0.05)[0]
            else None,
            has_pending_input_fn=lambda: bool(select.select([fd], [], [], 0.05)[0]),
            write_fn=lambda text: (output_stream.write(text), output_stream.flush()),
            reset_line_fn=lambda: (
                output_stream.write("\r\033[2K"),
                output_stream.write(prompt),
                output_stream.flush(),
            ),
        )
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
