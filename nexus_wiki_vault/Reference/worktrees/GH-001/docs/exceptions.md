---
id: exceptions
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
path: nexus_wiki_vault/06_Ops/Reference/worktrees/GH-001/docs/exceptions.md
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
# Exceptions

This page lists exceptions that may be raised when using HTTPX.

For an overview of how to work with HTTPX exceptions, see [Exceptions ([[quickstart|Quickstart]])]([[quickstart|quickstart]].md#exceptions).

## The exception hierarchy

* HTTPError
    * RequestError
        * TransportError
            * TimeoutException
                * ConnectTimeout
                * ReadTimeout
                * WriteTimeout
                * PoolTimeout
            * NetworkError
                * ConnectError
                * ReadError
                * WriteError
                * CloseError
            * ProtocolError
                * LocalProtocolError
                * RemoteProtocolError
            * ProxyError
            * UnsupportedProtocol
        * DecodingError
        * TooManyRedirects
    * HTTPStatusError
* InvalidURL
* CookieConflict
* StreamError
    * StreamConsumed
    * ResponseNotRead
    * RequestNotRead
    * StreamClosed

---

## Exception classes

::: httpx.HTTPError
    :docstring:

::: httpx.RequestError
    :docstring:

::: httpx.TransportError
    :docstring:

::: httpx.TimeoutException
    :docstring:

::: httpx.ConnectTimeout
    :docstring:

::: httpx.ReadTimeout
    :docstring:

::: httpx.WriteTimeout
    :docstring:

::: httpx.PoolTimeout
    :docstring:

::: httpx.NetworkError
    :docstring:

::: httpx.ConnectError
    :docstring:

::: httpx.ReadError
    :docstring:

::: httpx.WriteError
    :docstring:

::: httpx.CloseError
    :docstring:

::: httpx.ProtocolError
    :docstring:

::: httpx.LocalProtocolError
    :docstring:

::: httpx.RemoteProtocolError
    :docstring:

::: httpx.ProxyError
    :docstring:

::: httpx.UnsupportedProtocol
    :docstring:

::: httpx.DecodingError
    :docstring:

::: httpx.TooManyRedirects
    :docstring:

::: httpx.HTTPStatusError
    :docstring:

::: httpx.InvalidURL
    :docstring:

::: httpx.CookieConflict
    :docstring:

::: httpx.StreamError
    :docstring:

::: httpx.StreamConsumed
    :docstring:

::: httpx.StreamClosed
    :docstring:

::: httpx.ResponseNotRead
    :docstring:

::: httpx.RequestNotRead
    :docstring:


---
[[System Overview]]