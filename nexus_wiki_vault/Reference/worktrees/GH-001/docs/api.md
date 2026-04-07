---
id: api
type: doc
status: active
created: 2026-04-07T07:29:32Z
updated: 2026-04-07T07:29:32Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/worktrees/GH-001/docs/api.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
# Developer Interface

## Helper Functions

!!! note
    Only use these functions if you're [[testing]] HTTPX in a console
    or making a small number of requests. Using a `Client` will
    enable HTTP/2 and connection pooling for more efficient and
    long-lived connections.

::: httpx.request
    :docstring:

::: httpx.get
    :docstring:

::: httpx.[[options]]
    :docstring:

::: httpx.head
    :docstring:

::: httpx.post
    :docstring:

::: httpx.put
    :docstring:

::: httpx.patch
    :docstring:

::: httpx.delete
    :docstring:

::: httpx.stream
    :docstring:

## `Client`

::: httpx.Client
    :docstring:
    :members: headers cookies params auth request get head [[options]] post put patch delete stream build_request send close

## `AsyncClient`

::: httpx.AsyncClient
    :docstring:
    :members: headers cookies params auth request get head [[options]] post put patch delete stream build_request send aclose


## `Response`

*An HTTP response.*

* `def __init__(...)`
* `.status_code` - **int**
* `.reason_phrase` - **str**
* `.http_version` - `"HTTP/2"` or `"HTTP/1.1"`
* `.url` - **URL**
* `.headers` - **Headers**
* `.content` - **bytes**
* `.text` - **str**
* `.encoding` - **str**
* `.is_redirect` - **bool**
* `.request` - **Request**
* `.next_request` - **Optional[Request]**
* `.cookies` - **Cookies**
* `.history` - **List[Response]**
* `.elapsed` - **[timedelta](https://docs.python.org/3/library/datetime.html)**
  * The amount of time elapsed between sending the request and calling `close()` on the corresponding response received for that request.
  [total_seconds()](https://docs.python.org/3/library/datetime.html#datetime.timedelta.total_seconds) to correctly get
  the total elapsed seconds.
* `def .raise_for_status()` - **Response**
* `def .json()` - **Any**
* `def .read()` - **bytes**
* `def .iter_raw([chunk_size])` - **bytes iterator**
* `def .iter_bytes([chunk_size])` - **bytes iterator**
* `def .iter_text([chunk_size])` - **text iterator**
* `def .iter_lines()` - **text iterator**
* `def .close()` - **None**
* `def .next()` - **Response**
* `def .aread()` - **bytes**
* `def .aiter_raw([chunk_size])` - **[[async]] bytes iterator**
* `def .aiter_bytes([chunk_size])` - **[[async]] bytes iterator**
* `def .aiter_text([chunk_size])` - **[[async]] text iterator**
* `def .aiter_lines()` - **[[async]] text iterator**
* `def .aclose()` - **None**
* `def .anext()` - **Response**

## `Request`

*An HTTP request. Can be constructed explicitly for more control over exactly
what gets sent over the wire.*

```pycon
>>> request = httpx.Request("GET", "https://example.org", headers={'host': 'example.org'})
>>> response = client.send(request)
```

* `def __init__(method, url, [params], [headers], [cookies], [content], [data], [files], [json], [stream])`
* `.method` - **str**
* `.url` - **URL**
* `.content` - **byte**, **byte iterator**, or **byte [[async]] iterator**
* `.headers` - **Headers**
* `.cookies` - **Cookies**

## `URL`

*A normalized, IDNA supporting URL.*

```pycon
>>> url = URL("https://example.org/")
>>> url.host
'example.org'
```

* `def __init__(url, **kwargs)`
* `.scheme` - **str**
* `.authority` - **str**
* `.host` - **str**
* `.port` - **int**
* `.path` - **str**
* `.query` - **str**
* `.raw_path` - **str**
* `.fragment` - **str**
* `.is_ssl` - **bool**
* `.is_absolute_url` - **bool**
* `.is_relative_url` - **bool**
* `def .copy_with([scheme], [authority], [path], [query], [fragment])` - **URL**

## `Headers`

*A case-insensitive multi-dict.*

```pycon
>>> headers = Headers({'Content-Type': 'application/json'})
>>> headers['content-type']
'application/json'
```

* `def __init__(self, headers, encoding=None)`
* `def copy()` - **Headers**

## `Cookies`

*A dict-like cookie store.*

```pycon
>>> cookies = Cookies()
>>> cookies.set("name", "value", domain="example.org")
```

* `def __init__(cookies: [dict, Cookies, CookieJar])`
* `.jar` - **CookieJar**
* `def extract_cookies(response)`
* `def set_cookie_header(request)`
* `def set(name, value, [domain], [path])`
* `def get(name, [domain], [path])`
* `def delete(name, [domain], [path])`
* `def clear([domain], [path])`
* *Standard mutable mapping interface*

## `Proxy`

*A configuration of the proxy server.*

```pycon
>>> proxy = Proxy("http://proxy.example.com:8030")
>>> client = Client(proxy=proxy)
```

* `def __init__(url, [ssl_context], [auth], [headers])`
* `.url` - **URL**
* `.auth` - **tuple[str, str]**
* `.headers` - **Headers**
* `.ssl_context` - **SSLContext**


---
[[System Overview]]