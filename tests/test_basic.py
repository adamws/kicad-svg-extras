"""Basic tests for kicad-svg-extras."""

import subprocess


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
