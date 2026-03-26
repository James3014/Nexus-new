import codecs
import os
import select
import sys
from typing import Optional

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
except Exception:  # pragma: no cover
    PromptSession = None
    KeyBindings = None

BRACKETED_PASTE_START = b"\x1b[200~"
BRACKETED_PASTE_END = b"\x1b[201~"
_PROMPT_SESSION = None


def _build_prompt_toolkit_session():
    if PromptSession is None or KeyBindings is None:
        return None

    bindings = KeyBindings()

    @bindings.add("escape")
    def _clear(event):
        event.app.current_buffer.reset()

    return PromptSession(
        multiline=False,
        key_bindings=bindings,
        wrap_lines=True,
    )


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
    buffer = []
    decoder = codecs.getincrementaldecoder("utf-8")()
    has_pending_input_fn = has_pending_input_fn or (lambda: False)
    reset_line_fn = reset_line_fn or (lambda: None)
    saw_newline = False
    escape_buffer = bytearray()
    pending_escape = False

    while True:
        chunk = read_byte_fn()
        if chunk is None:
            if pending_escape:
                buffer = []
                decoder = codecs.getincrementaldecoder("utf-8")()
                saw_newline = False
                pending_escape = False
                escape_buffer.clear()
                reset_line_fn()
                continue
            if buffer and saw_newline:
                write_fn("\n")
                return "".join(buffer)
            continue
        if not chunk:
            if buffer:
                write_fn("\n")
                return "".join(buffer)
            raise EOFError

        if chunk in (b"\r", b"\n"):
            write_fn("\n")
            saw_newline = True
            if has_pending_input_fn():
                buffer.append("\n")
                continue
            return "".join(buffer)

        if chunk == b"\x04":
            if buffer:
                write_fn("\n")
                return "".join(buffer)
            raise EOFError

        if chunk in (b"\x7f", b"\b"):
            if buffer:
                buffer.pop()
                write_fn("\b \b")
            continue

        if escape_buffer or chunk == b"\x1b":
            escape_buffer.extend(chunk)
            if bytes(escape_buffer) == b"\x1b":
                pending_escape = True
                continue
            if bytes(escape_buffer) == BRACKETED_PASTE_START:
                pending_escape = False
                escape_buffer.clear()
                continue
            if bytes(escape_buffer) == BRACKETED_PASTE_END:
                pending_escape = False
                escape_buffer.clear()
                write_fn("\n")
                return "".join(buffer)
            if BRACKETED_PASTE_START.startswith(bytes(escape_buffer)) or BRACKETED_PASTE_END.startswith(bytes(escape_buffer)):
                continue
            if bytes(escape_buffer).startswith(b"\x1b["):
                pending_escape = False
                escape_buffer.clear()
                continue
            buffer = []
            decoder = codecs.getincrementaldecoder("utf-8")()
            saw_newline = False
            pending_escape = False
            escape_buffer.clear()
            reset_line_fn()
            continue

        try:
            text = decoder.decode(chunk)
        except UnicodeDecodeError:
            continue

        if not text:
            continue

        buffer.append(text)
        write_fn(text)


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
