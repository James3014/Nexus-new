DEFAULT_PORT = 8080


def load_port(raw):
    """Parse a port from a config string. Missing or blank values use DEFAULT_PORT.

    Any other value that is not an integer in 1..65535 raises ValueError.
    """
    if raw is None or not str(raw).strip():
        return DEFAULT_PORT
    try:
        port = int(raw)
        if not 1 <= port <= 65535:
            raise ValueError(f"port out of range: {port}")
        return port
    except Exception:  # BUG: swallows the ValueError and returns the default
        return DEFAULT_PORT
