"""Basic tests for kicad-svg-extras."""

import os
import subprocess

import pytest


def test_cli_help():
    """Test that the CLI help works."""
    cmd = ["python", "-m", "src.kicad_svg_extras", "--help"]
    result = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, check=False
    )

    # If pcbnew is not available, the import will fail - skip this test
    if result.returncode != 0 and "pcbnew module not available" in result.stderr:
        pytest.skip("pcbnew module not available - KiCad Python API not accessible")

    assert result.returncode == 0
    assert "Generate SVG files with custom per-net colors" in result.stdout


def test_kicad_cli_available():
    """Test that KiCad CLI is available."""
    # Use nightly version if environment variable is set
    kicad_cmd = "kicad-cli-nightly" if os.getenv("KICAD_NIGHTLY") else "kicad-cli"

    try:
        result = subprocess.run(  # noqa: S603
            [kicad_cmd, "version"], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0
        assert "9." in result.stdout
    except FileNotFoundError:
        # Skip test if KiCad is not installed
        pytest.skip(f"{kicad_cmd} not found")
