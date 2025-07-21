# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Basic tests for kicad-svg-extras."""

import subprocess

import pytest


@pytest.mark.functional
def test_cli_help():
    """Test that the CLI help works."""
    result = subprocess.run(
        ["kicad-svg-extras", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Generate SVG files with custom per-net colors" in result.stdout


@pytest.mark.functional
def test_kicad_cli_available():
    """Test that KiCad CLI is available."""
    result = subprocess.run(
        ["kicad-cli", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "9." in result.stdout
