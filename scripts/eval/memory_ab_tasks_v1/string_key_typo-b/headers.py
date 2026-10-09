def content_type(headers):
    """Content-Type header value, defaulting to text/plain."""
    return headers.get("content_type", "text/plain")  # BUG: key typo, should be "Content-Type"
