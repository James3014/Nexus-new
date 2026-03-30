import pytest
from nexus.pilot_cli.input_engine import collect_cbreak_text, BRACKETED_PASTE_START, BRACKETED_PASTE_END

def test_collect_cbreak_simple_input():
    input_bytes = [b"h", b"e", b"l", b"l", b"o", b"\n"]
    idx = 0
    def read_byte():
        nonlocal idx
        if idx < len(input_bytes):
            res = input_bytes[idx]
            idx += 1
            return res
        return b""

    output = []
    def write_fn(text):
        output.append(text)

    result = collect_cbreak_text(read_byte, write_fn)
    assert result == "hello"

def test_collect_cbreak_backspace():
    input_bytes = [b"a", b"b", b"\x7f", b"c", b"\n"]
    idx = 0
    def read_byte():
        nonlocal idx
        if idx < len(input_bytes):
            res = input_bytes[idx]
            idx += 1
            return res
        return b""

    output = []
    result = collect_cbreak_text(read_byte, lambda t: output.append(t))
    assert result == "ac"

def test_bracketed_paste_mode():
    # Simulate a paste: [START] content [END]
    # Split the ESC sequence to test buffering
    input_bytes = [b"\x1b", b"[", b"2", b"0", b"0", b"~", b"p", b"a", b"s", b"t", b"e", b"\x1b", b"[", b"2", b"0", b"1", b"~"]
    idx = 0
    def read_byte():
        nonlocal idx
        if idx < len(input_bytes):
            res = input_bytes[idx]
            idx += 1
            return res
        return b""

    result = collect_cbreak_text(read_byte, lambda t: None)
    assert result == "paste"

def test_large_paste_fragmentation():
    # Simulate a large paste that might be fragmented at the byte level
    large_text = "x" * 1000
    # Markers as individual bytes, text as chunks
    start_marker = [b"\x1b", b"[", b"2", b"0", b"0", b"~"]
    end_marker = [b"\x1b", b"[", b"2", b"0", b"1", b"~"]
    input_series = start_marker + [large_text[i:i+10].encode() for i in range(0, 1000, 10)] + end_marker
    
    idx = 0
    def read_byte():
        nonlocal idx
        if idx < len(input_series):
            res = input_series[idx]
            idx += 1
            return res
        return b""

    result = collect_cbreak_text(read_byte, lambda t: None)
    assert result == large_text
