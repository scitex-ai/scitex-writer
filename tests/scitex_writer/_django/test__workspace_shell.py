#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The workspace-shell downgrade message must name the RIGHT failure.

`except ImportError` around `scitex_sdk.app.embed` catches two failures — the
package being absent, and the package being present but older than the release
that added `.embed` — and the old code reported the first for both. A user who
reads "scitex-sdk is not installed", runs `pip show scitex-sdk`, and finds it
sitting right there concludes the message is lying, and goes and debugs
something else. That is the same defect as a remedy that does nothing: the
signal is present and wrong, which is worse than absent.

`describe_missing_shell` is pure so these run against real values with no mock
and no monkeypatch (PA-306 / STX-NM002).
"""

from scitex_writer._django._workspace_shell import (
    MIN_SCITEX_SDK,
    REMEDY,
    describe_missing_shell,
)


class TestAbsentPackage:
    def test_absent_package_is_reported_as_not_installed(self):
        # Arrange
        spec_found = False

        # Act
        reason = describe_missing_shell(spec_found, installed_version=None)

        # Assert
        assert reason == "scitex-sdk is not installed"


class TestPresentButTooOld:
    def test_present_but_old_package_names_the_installed_version(self):
        # Arrange
        installed = "0.2.1"

        # Act
        reason = describe_missing_shell(True, installed_version=installed)

        # Assert
        assert installed in reason

    def test_present_but_old_package_never_claims_not_installed(self):
        # This is the regression. The old code said exactly this, and it was
        # false: the package WAS installed, just too old to expose `.embed`.
        # Arrange
        installed = "0.2.1"

        # Act
        reason = describe_missing_shell(True, installed_version=installed)

        # Assert
        assert "not installed" not in reason

    def test_present_but_old_package_names_the_required_floor(self):
        # Arrange
        installed = "0.2.1"

        # Act
        reason = describe_missing_shell(True, installed_version=installed)

        # Assert
        assert MIN_SCITEX_SDK in reason

    def test_present_with_unknown_version_still_avoids_not_installed(self):
        # Arrange: a package on sys.path with no distribution metadata. We
        # still know it is THERE, so calling it absent would be just as wrong.
        unknown = None

        # Act
        reason = describe_missing_shell(True, installed_version=unknown)

        # Assert
        assert "not installed" not in reason


class TestRemedy:
    def test_remedy_installs_the_all_extra(self):
        # Arrange: extras are all-or-nothing. A remedy naming a retired
        # fine-grained extra would install nothing at all.
        expected = "uv pip install 'scitex-writer[all]'"

        # Act
        offered = REMEDY

        # Assert
        assert offered == expected
