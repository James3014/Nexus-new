---
id: support-multiple-versions
type: doc
status: active
created: 2026-04-07T07:29:35Z
updated: 2026-04-07T07:29:35Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/benchmarks/click/docs/support-multiple-versions.md
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
# Supporting Multiple Versions

If you are a library maintainer, you may want to support multiple versions of
Click. See the Pallets [version policy] for information about our version
numbers and support policy.

[version policy]: https://palletsprojects.com/versions

Most features of Click are stable across releases, and don't require special
handling. However, feature releases may deprecate and change APIs. Occasionally,
a change will require special handling.

## Use Feature Detection

Prefer using feature detection. Looking at the version can be tempting, but is
often more brittle or results in more complicated code. Try to use `if` or `try`
blocks to decide whether to use a new or old pattern.

If you do need to look at the version, use {func}`importlib.metadata.version`,
the standardized way to get versions for any installed Python package.

## Changes in 8.2

### `ParamType` methods require `ctx`

In 8.2, several methods of `ParamType` now have a `ctx: click.Context`
argument. Because this changes the signature of the methods from 8.1, it's not
obvious how to support both when subclassing or calling.

This example uses `ParamType.get_metavar`, and the same technique should be
applicable to other methods such as `get_missing_message`.

Update your methods overrides to take the new `ctx` argument. Use the
following decorator to wrap each method. In 8.1, it will get the context where
possible and pass it using the 8.2 signature.

```python
import functools
import typing as t
import click

F = t.TypeVar("F", bound=t.Callable[..., t.Any])

def add_ctx_arg(f: F) -> F:
    @functools.wraps(f)
    def wrapper(*args: t.Any, **kwargs: t.Any) -> t.Any:
        if "ctx" not in kwargs:
            kwargs["ctx"] = click.get_current_context(silent=True)

        return f(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
```

Here's an example ``ParamType`` subclass which uses this:

```python
class CommaDelimitedString(click.ParamType):
    @add_ctx_arg
    def get_metavar(self, param: click.Parameter, ctx: click.Context | None) -> str:
        return "TEXT,TEXT,..."
```


---
[[System Overview]]