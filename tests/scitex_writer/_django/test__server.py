#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_django/_server.py

"""`run()` must not hide a broken editor behind a working-looking one.

Why this file exists: `run()` used to wrap `django.setup()`, the `migrate`
call, AND the `scitex_app` import in a single `try/except ImportError: pass`.
Any ImportError raised anywhere in that block — a broken Django app, a
half-installed dependency — was swallowed, and the editor silently downgraded
to a bare runserver without the workspace shell. The operator saw a server
come up with no way to know it was the degraded one.

The optional-dependency downgrade is legitimate, but it must be the ONLY thing
that except clause can catch, and it must announce itself. Everything else
propagates. This is the same silent-fallback family as the port slide that
`gui serve` used to do (bind the next free port instead of failing).

These tests read the function's own syntax tree, so a future edit that widens
the except back over `django.setup()` fails HERE instead of in production.
"""

import ast
import inspect
import textwrap

from scitex_writer._django import _server

_RUN_TREE = ast.parse(textwrap.dedent(inspect.getsource(_server.run)))


def _import_guarded_try_blocks() -> list[ast.Try]:
    """Every `try` in `run()` whose handlers catch ImportError."""
    return [
        node
        for node in ast.walk(_RUN_TREE)
        if isinstance(node, ast.Try)
        and any(
            isinstance(handler.type, ast.Name) and handler.type.id == "ImportError"
            for handler in node.handlers
        )
    ]


def test_import_guard_protects_only_import_statements():
    # Arrange
    guarded_statements = [
        statement for block in _import_guarded_try_blocks() for statement in block.body
    ]
    # Act
    non_imports = [
        statement
        for statement in guarded_statements
        if not isinstance(statement, (ast.Import, ast.ImportFrom))
    ]
    # Assert
    assert non_imports == []


def test_import_guard_announces_the_degraded_fallback():
    # Arrange
    handlers = [
        handler for block in _import_guarded_try_blocks() for handler in block.handlers
    ]
    # Act
    handler_source = " ".join(
        ast.dump(statement) for handler in handlers for statement in handler.body
    )
    # Assert
    assert "print" in handler_source


def test_django_setup_is_never_import_guarded():
    # Arrange
    guarded_nodes = {
        id(node)
        for block in _import_guarded_try_blocks()
        for statement in block.body
        for node in ast.walk(statement)
    }
    # Act
    guarded_setup_calls = [
        node
        for node in ast.walk(_RUN_TREE)
        if isinstance(node, ast.Attribute)
        and node.attr == "setup"
        and id(node) in guarded_nodes
    ]
    # Assert
    assert guarded_setup_calls == []


# ---------------------------------------------------------------------------
# ALLOWED_HOSTS: binding an address must permit it, and must not permit
# anything else.
#
# Why: ALLOWED_HOSTS was a hardcoded loopback list, so `serve --host
# <non-loopback>` started cleanly, printed a correct-looking URL, and then
# answered 400 Bad Request to every caller. Nothing in the banner was wrong,
# which is why it read as a firewall problem rather than a bug. Reported by
# scitex-scholar 2026-08-23, who found the identical list in figrecipe,
# storage and scholar -- a shared ancestor in the scitex-app SDK.
#
# The pairing matters more than either half: the fix must open the bound
# address AND leave everything else shut. Writer ships no authentication, so
# a wildcard would turn every reachable address into an unauthenticated
# reader.
# ---------------------------------------------------------------------------

import os  # noqa: E402

import pytest  # noqa: E402

from scitex_writer._django._server import (  # noqa: E402
    contribute_allowed_host,
    warn_if_wildcard_bind,
)

_ENV = "SCITEX_WRITER_ALLOWED_HOSTS"


@pytest.fixture
def clean_allowed_hosts_env():
    """Start from no operator entries and put the real environment back.

    Plain save/restore on os.environ -- no monkeypatch -- so the test runs
    against the same environment the server does.
    """
    saved = os.environ.pop(_ENV, None)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop(_ENV, None)
        else:
            os.environ[_ENV] = saved


class TestAllowedHosts:
    def test_bound_host_becomes_allowed(self, clean_allowed_hosts_env):
        # Arrange
        host = "writer.example.test"
        # Act
        allowed = contribute_allowed_host(host)
        # Assert
        assert host in allowed

    def test_bound_host_is_exported_for_settings_to_read(self, clean_allowed_hosts_env):
        """settings.py reads the env var, so contributing to the list is not
        enough -- it has to reach the environment before Django imports."""
        # Arrange
        host = "writer.example.test"
        # Act
        contribute_allowed_host(host)
        # Assert
        assert host in os.environ[_ENV].split(",")

    def test_operator_entries_are_kept(self, clean_allowed_hosts_env):
        """Appended, never assigned: a value the operator set must survive."""
        # Arrange
        os.environ[_ENV] = "proxy.example.test"
        # Act
        allowed = contribute_allowed_host("writer.example.test")
        # Assert
        assert allowed == ["proxy.example.test", "writer.example.test"]

    def test_nothing_else_is_permitted(self, clean_allowed_hosts_env):
        """The negative half. A fix that opened everything would pass every
        test above and be far worse than the defect it replaced."""
        # Arrange
        host = "writer.example.test"
        # Act
        allowed = contribute_allowed_host(host)
        # Assert
        assert "*" not in allowed

    def test_repeated_bind_does_not_duplicate(self, clean_allowed_hosts_env):
        # Arrange
        contribute_allowed_host("writer.example.test")
        # Act
        allowed = contribute_allowed_host("writer.example.test")
        # Assert
        assert allowed.count("writer.example.test") == 1

    def test_wildcard_bind_with_no_named_host_warns(self, clean_allowed_hosts_env):
        """0.0.0.0 names no host, so bind-implies-permission cannot resolve it."""
        # Arrange
        allowed = contribute_allowed_host("0.0.0.0")
        # Act
        warning = warn_if_wildcard_bind("0.0.0.0", allowed)
        # Assert
        assert warning is not None

    def test_wildcard_warning_names_the_remedy(self, clean_allowed_hosts_env):
        """An error that only states what broke is half-written."""
        # Arrange
        allowed = contribute_allowed_host("0.0.0.0")
        # Act
        warning = warn_if_wildcard_bind("0.0.0.0", allowed)
        # Assert
        assert _ENV in warning

    def test_wildcard_bind_with_a_named_host_is_silent(self, clean_allowed_hosts_env):
        """Positive control: the warning must be able to NOT fire, or it is
        noise that trains people to ignore it."""
        # Arrange
        os.environ[_ENV] = "writer.example.test"
        allowed = contribute_allowed_host("0.0.0.0")
        # Act
        warning = warn_if_wildcard_bind("0.0.0.0", allowed)
        # Assert
        assert warning is None

    def test_loopback_bind_does_not_warn(self, clean_allowed_hosts_env):
        # Arrange
        allowed = contribute_allowed_host("127.0.0.1")
        # Act
        warning = warn_if_wildcard_bind("127.0.0.1", allowed)
        # Assert
        assert warning is None
