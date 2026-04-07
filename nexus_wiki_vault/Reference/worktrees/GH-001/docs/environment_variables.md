---
id: environment_variables
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
path: nexus_wiki_vault/06_Ops/Reference/worktrees/GH-001/docs/environment_variables.md
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
# Environment Variables

The HTTPX library can be configured via environment variables.
Environment variables are used by default. To ignore environment variables, `trust_env` has to be set `False`. There are two ways to set `trust_env` to disable environment variables:

* On the client via `httpx.Client(trust_env=False)`.
* Using the top-level [[api|API]], such as `httpx.get("<url>", trust_env=False)`.

Here is a list of environment variables that HTTPX recognizes and what function they serve:

## [[proxies]]

The environment variables documented below are used as a convention by various HTTP tooling, including:

* [cURL](https://github.com/curl/curl/blob/master/docs/MANUAL.md#environment-variables)
* [requests](https://github.com/psf/requests/blob/master/docs/user/advanced.rst#[[proxies|proxies]])

For more information on using [[proxies]] in HTTPX, see [HTTP Proxying](advanced/[[proxies|proxies]].md#http-proxying).

### `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`

Valid values: A URL to a proxy

`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` set the proxy to be used for `http`, `https`, or all requests respectively.

```bash
export HTTP_PROXY=http://my-external-proxy.com:1234

# This request will be sent through the proxy
python -c "import httpx; httpx.get('http://example.com')"

# This request will be sent directly, as we set `trust_env=False`
python -c "import httpx; httpx.get('http://example.com', trust_env=False)"

```

### `NO_PROXY`

Valid values: a comma-separated list of hostnames/urls

`NO_PROXY` disables the proxy for specific urls

```bash
export HTTP_PROXY=http://my-external-proxy.com:1234
export NO_PROXY=http://127.0.0.1,python-httpx.org

# As in the previous example, this request will be sent through the proxy
python -c "import httpx; httpx.get('http://example.com')"

# These requests will be sent directly, bypassing the proxy
python -c "import httpx; httpx.get('http://127.0.0.1:5000/my-[[api|api]]')"
python -c "import httpx; httpx.get('https://www.python-httpx.org')"
```

## `SSL_CERT_FILE`

Valid values: a filename

If this environment variable is set then HTTPX will load
CA certificate from the specified file instead of the default
location.

Example:

```console
SSL_CERT_FILE=/path/to/ca-certs/ca-bundle.crt python -c "import httpx; httpx.get('https://example.com')"
```

## `SSL_CERT_DIR`

Valid values: a directory following an [OpenSSL specific layout](https://www.openssl.org/docs/manmaster/man3/SSL_CTX_load_verify_locations.html).

If this environment variable is set and the directory follows an [OpenSSL specific layout](https://www.openssl.org/docs/manmaster/man3/SSL_CTX_load_verify_locations.html) (ie. you ran `c_rehash`) then HTTPX will load CA certificates from this directory instead of the default location.

Example:

```console
SSL_CERT_DIR=/path/to/ca-certs/ python -c "import httpx; httpx.get('https://example.com')"
```


---
[[System Overview]]