from app import handler


def test_handler_strips_whitespace():
    assert handler("  value ") == "value"
