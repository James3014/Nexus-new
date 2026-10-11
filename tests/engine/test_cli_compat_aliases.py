from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def test_root_research_sprint_alias_explains_retirement():
    """The alias must not forward to a nested command that does not exist."""
    res = CliRunner().invoke(cli_mod.nexus, ["research:sprint", "--task", "x"])

    assert res.exit_code == 2
    assert "research:auto-flow" in res.output
    assert "Forwarding now" not in res.output
