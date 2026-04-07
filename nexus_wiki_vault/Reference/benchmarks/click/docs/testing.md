---
id: testing
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
path: nexus_wiki_vault/06_Ops/Reference/benchmarks/click/docs/testing.md
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
# Testing Click Applications

```{eval-rst}
.. currentmodule:: click.testing
```

Click provides the {ref}`click.testing <testing>` module to help you invoke command line applications and check their behavior.

These tools should only be used for testing since they change
the entire interpreter state for simplicity. They are not thread-safe!

The examples use [pytest](https://docs.pytest.org/en/stable/) style tests.

```{contents}
:depth: 1
:local: true
```

## Basic Example

The key pieces are:
  - {class}`CliRunner` - used to invoke commands as command line scripts.
  - {class}`Result` - returned from {meth}`CliRunner.invoke`. Captures output data, exit code, optional exception, and captures the output as bytes and binary data.

```{code-block} python
:caption: hello.py

import click

@click.command()
@click.argument('name')
def hello(name):
   click.echo(f'Hello {name}!')
```

```{code-block} python
:caption: test_hello.py

from click.testing import CliRunner
from hello import hello

def test_hello_world():
  runner = CliRunner()
  result = runner.invoke(hello, ['Peter'])
  assert result.exit_code == 0
  assert result.output == 'Hello Peter!\n'
```

## Subcommands

A subcommand name must be specified in the `args` parameter {meth}`CliRunner.invoke`:

```{code-block} python
:caption: sync.py

import click

@click.group()
@click.option('--debug/--no-debug', default=False)
def cli(debug):
   click.echo(f"Debug mode is {'on' if debug else 'off'}")

@cli.command()
def sync():
   click.echo('Syncing')
```

```{code-block} python
:caption: test_sync.py

from click.testing import CliRunner
from sync import cli

def test_sync():
  runner = CliRunner()
  result = runner.invoke(cli, ['--debug', 'sync'])
  assert result.exit_code == 0
  assert 'Debug mode is on' in result.output
  assert 'Syncing' in result.output
```

## Context Settings

Additional keyword arguments passed to {meth}`CliRunner.invoke` will be used to construct the initial {class}`Context object <click.Context>`.
For example, setting a fixed terminal width equal to 60:

```{code-block} python
:caption: sync.py

import click

@click.group()
def cli():
   pass

@cli.command()
def sync():
   click.echo('Syncing')
```

```{code-block} python
:caption: test_sync.py

from click.testing import CliRunner
from sync import cli

def test_sync():
  runner = CliRunner()
  result = runner.invoke(cli, ['sync'], terminal_width=60)
  assert result.exit_code == 0
  assert 'Debug mode is on' in result.output
  assert 'Syncing' in result.output
```

## File System Isolation

The {meth}`CliRunner.isolated_filesystem` context manager sets the current working directory to a new, empty folder.

```{code-block} python
:caption: cat.py

import click

@click.command()
@click.argument('f', type=click.File())
def cat(f):
   click.echo(f.read())
```

```{code-block} python
:caption: test_cat.py

from click.testing import CliRunner
from cat import cat

def test_cat():
   runner = CliRunner()
   with runner.isolated_filesystem():
      with open('hello.txt', 'w') as f:
          f.write('Hello World!')

      result = runner.invoke(cat, ['hello.txt'])
      assert result.exit_code == 0
      assert result.output == 'Hello World!\n'
```

Pass in a path to control where the temporary directory is created.
In this case, the directory will not be removed by Click. Its useful
to integrate with a framework like Pytest that manages temporary files.

```{code-block} python
:caption: test_cat.py

from click.testing import CliRunner
from cat import cat

def test_cat_with_path_specified():
   runner = CliRunner()
   with runner.isolated_filesystem('~/test_folder'):
      with open('hello.txt', 'w') as f:
          f.write('Hello World!')

      result = runner.invoke(cat, ['hello.txt'])
      assert result.exit_code == 0
      assert result.output == 'Hello World!\n'
```

## Input Streams

The test wrapper can provide input data for the input stream (stdin). This is very useful for testing prompts.

```{code-block} python
:caption: prompt.py

import click

@click.command()
@click.option('--foo', prompt=True)
def prompt(foo):
   click.echo(f"foo={foo}")
```

```{code-block} python
:caption: test_prompt.py

from click.testing import CliRunner
from prompt import prompt

def test_prompts():
   runner = CliRunner()
   result = runner.invoke(prompt, input='wau wau\n')
   assert not result.exception
   assert result.output == 'Foo: wau wau\nfoo=wau wau\n'
```

Prompts will be emulated so they write the input data to
the output stream as well. If hidden input is expected then this
does not happen.


---
[[System Overview]]