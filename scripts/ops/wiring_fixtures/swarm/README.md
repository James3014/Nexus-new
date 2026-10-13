# Swarm fixture

`calc.py` subtracts instead of adding; `repro.py` is the verify script. The audit commits this
workspace to a scratch git repository, then the swarm executor locks `calc.py`, forks one
`BattleSwarm` worktree per strategy, lets the local worker (M5 tunnel, armored local lane) write
and commit a candidate in each worktree, runs `repro.py` there and offers the verified winner to
the single Candidate integration owner (`SelfHostedTaskService.integrate_approved`, which
delegates to `ControlledIntegrationManager`).
