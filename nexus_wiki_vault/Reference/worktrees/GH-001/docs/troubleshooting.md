---
id: troubleshooting
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
path: nexus_wiki_vault/06_Ops/Reference/worktrees/GH-001/docs/troubleshooting.md
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
# Troubleshooting

This page lists some common problems or issues you could encounter while developing with HTTPX, as well as possible solutions.

## [[proxies]]

---

### "`The handshake operation timed out`" on HTTPS requests when using a proxy

**Description**: When using a proxy and making an HTTPS request, you see an exception looking like this:

```console
httpx.ProxyError: _ssl.c:1091: The handshake operation timed out
```

**Similar issues**: [encode/httpx#1412](https://github.com/encode/httpx/issues/1412), [encode/httpx#1433](https://github.com/encode/httpx/issues/1433)

**Resolution**: it is likely that you've set up your [[proxies]] like this...

```python
mounts = {
  "http://": httpx.HTTPTransport(proxy="http://myproxy.org"),
  "https://": httpx.HTTPTransport(proxy="https://myproxy.org"),
}
```

Using this setup, you're telling HTTPX to connect to the proxy using HTTP for HTTP requests, and using HTTPS for HTTPS requests.

But if you get the error above, it is likely that your proxy doesn't support connecting via HTTPS. Don't worry: that's a [common gotcha](advanced/[[proxies|proxies]].md#http-[[proxies|proxies]]).

Change the scheme of your HTTPS proxy to `http://...` instead of `https://...`:

```python
mounts = {
  "http://": httpx.HTTPTransport(proxy="http://myproxy.org"),
  "https://": httpx.HTTPTransport(proxy="http://myproxy.org"),
}
```

This can be simplified to:

```python
proxy = "http://myproxy.org"
with httpx.Client(proxy=proxy) as client:
  ...
```

For more information, see [[[proxies|Proxies]]: FORWARD vs TUNNEL](advanced/[[proxies|proxies]].md#forward-vs-tunnel).

---

### Error when making requests to an HTTPS proxy

**Description**: your proxy _does_ support connecting via HTTPS, but you are seeing errors along the lines of...

```console
httpx.ProxyError: [[[ssl|SSL]]: PRE_MAC_LENGTH_TOO_LONG] invalid alert (_ssl.c:1091)
```

**Similar issues**: [encode/httpx#1424](https://github.com/encode/httpx/issues/1424).

**Resolution**: HTTPX does not properly support HTTPS [[proxies]] at this time. If that's something you're interested in having, please see [encode/httpx#1434](https://github.com/encode/httpx/issues/1434) and consider lending a hand there.


---
[[System Overview]]