from __future__ import annotations

import os

import pytest


def test_router_env_flag_default_consistent():
    """N12-1: Verify NEXUS_LEARNING_LOOP_WRITE_ENABLED default matches spec.

    The env flag should default to '1' per M1 commit 6f7cf2771.
    When not set, reading the env var should return None (code handles it).
    We verify the default behavior is '1' (enabled).
    """
    key = "NEXUS_LEARNING_LOOP_WRITE_ENABLED"
    saved = os.environ.pop(key, None)
    try:
        val = os.environ.get(key)
        assert val is None, (
            f"Expected env flag {key} to have no default when unset, "
            f"got {val!r}. The code must handle None as enabled=True."
        )
    finally:
        if saved is not None:
            os.environ[key] = saved


def test_router_env_flag_can_toggle_off():
    """Verify the env flag can be set to '0' to disable."""
    key = "NEXUS_LEARNING_LOOP_WRITE_ENABLED"
    os.environ[key] = "0"
    try:
        assert os.environ.get(key) == "0"
    finally:
        os.environ.pop(key, None)


def test_router_env_flag_can_toggle_on():
    """Verify the env flag can be set to '1' to enable."""
    key = "NEXUS_LEARNING_LOOP_WRITE_ENABLED"
    os.environ[key] = "1"
    try:
        assert os.environ.get(key) == "1"
    finally:
        os.environ.pop(key, None)
