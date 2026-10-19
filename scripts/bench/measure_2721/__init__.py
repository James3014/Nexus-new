"""Measurement harness for Nexus-new #2721 (bare vs Nexus P1, same model).

Step-3 tooling only: it materializes held-out tasks, runs the BARE / NOOP
arms, drives the NEXUS arm against a configurable (never the live :8766)
Gateway, blinds the candidates and proves input symmetry with a zero-model
dry run.  It never scores and never reads hidden tests into any arm input.
"""
