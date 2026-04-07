---
id: faqs
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
path: nexus_wiki_vault/06_Ops/Reference/benchmarks/click/docs/faqs.md
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
# Frequently Asked Questions

```{contents}
:depth: 2
:local: true
```

## General

### Shell Variable Expansion On Windows

I have a simple Click app :

```
import click

@click.command()
@click.argument('message')
def main(message: str):
    click.echo(message)

if __name__ == '__main__':
    main()

```

When you pass an environment variable in the argument, it expands it:

```{code-block} powershell
> Desktop python foo.py '$M0/.viola/2025-01-25-17-20-23-307878'
> M:/[[System Overview|home]]/ramrachum/.viola/2025-01-25-17-20-23-307878
>
```
Note that I used single quotes above, so my shell is not expanding the environment variable, Click does. How do I get Click to not expand it?

#### Answer

If you don't want Click to emulate (as best it can) unix expansion on Windows, pass windows_expand_args=False when calling the CLI.
Windows command line doesn't do any *, ~, or $ENV expansion. It also doesn't distinguish between double quotes and single quotes (where the later means "don't expand here"). Click emulates the expansion so that the app behaves similarly on both platforms, but doesn't receive information about what quotes were used.


---
[[System Overview]]