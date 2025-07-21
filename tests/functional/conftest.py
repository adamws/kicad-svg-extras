# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Pytest configuration and fixtures for functional tests."""

import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import pytest

try:
    import svgpathtools
except ImportError:
    svgpathtools = None

# We'll use the plugin manager to check for pytest-html availability

# Test data paths
FUNCTIONAL_DIR = Path(__file__).parent
DATA_DIR = FUNCTIONAL_DIR / "data"
PCB_FILES_DIR = DATA_DIR / "pcb_files"
CONFIG_FILES_DIR = DATA_DIR / "config_files"
REFERENCES_DIR = FUNCTIONAL_DIR / "references"


@pytest.fixture
def temp_output_dir():
    """Create temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def pcb_files_dir() -> Path:
    """Path to PCB test files directory."""
    return PCB_FILES_DIR


@pytest.fixture
def reference_dir() -> Path:
    """Get reference directory."""
    # Ensure the references directory exists
    REFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    return REFERENCES_DIR


@pytest.fixture
def cli_runner(request):
    """Helper for running kicad-svg-extras CLI commands with auto output capture."""

    def run_cli(
        args: list, cwd: Optional[Path] = None, *, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run kicad-svg-extras CLI with given arguments."""
        cmd = ["kicad-svg-extras", *args]
        result = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, check=check, cwd=cwd, timeout=60
        )

        # Automatically capture CLI output if capture_outputs fixture is available
        if hasattr(request.node, "_pytest_html_cli_outputs"):
            cmd_str = " ".join(cmd)
            cli_outputs = getattr(request.node, "_pytest_html_cli_outputs", [])
            cli_outputs.append(
                {
                    "command": cmd_str,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                }
            )
            request.node._pytest_html_cli_outputs = cli_outputs

        return result

    return run_cli


@pytest.fixture
def sample_configs() -> dict[str, Path]:
    """Dictionary of sample configuration files."""
    return {
        "basic": CONFIG_FILES_DIR / "basic_colors.json",
        "advanced": CONFIG_FILES_DIR / "advanced_nets.json",
    }


def pytest_configure(config):
    """Configure pytest markers for functional tests."""
    config.addinivalue_line(
        "markers",
        "requires_pcb_file: mark test as requiring a specific PCB file to be provided",
    )
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """Modify test collection to handle PCB file requirements."""
    skip_pcb_tests = pytest.mark.skip(reason="PCB file not provided yet")

    for item in items:
        if "requires_pcb_file" in item.keywords:
            # Check if any PCB files exist in test data
            if not any(PCB_FILES_DIR.glob("**/*.kicad_pcb")):
                item.add_marker(skip_pcb_tests)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):  # noqa: ARG001
    """Hook to add generated SVG images to HTML report."""
    outcome = yield
    report = outcome.get_result()

    # Only add extras on test call (not setup/teardown)
    pytest_html = item.config.pluginmanager.getplugin("html")
    if pytest_html and report.when == "call":
        extras = getattr(report, "extras", [])

        # Look for test output directories in the test function
        test_name = item.name

        # Try to find output directories created during the test
        # We'll look for temporary directories with generated SVGs
        if hasattr(item, "_pytest_html_capture"):
            # If we stored output directories during test execution
            output_dirs = getattr(item, "_pytest_html_capture", [])
            existing_dirs = [
                Path(output_dir)
                for output_dir in output_dirs
                if Path(output_dir).exists()
            ]
            if existing_dirs:
                _add_all_svg_files_to_report(
                    extras, existing_dirs, test_name, pytest_html
                )

        # Also capture CLI outputs if they were stored
        if hasattr(item, "_pytest_html_cli_outputs"):
            cli_outputs = getattr(item, "_pytest_html_cli_outputs", [])
            _add_cli_outputs_to_report(extras, cli_outputs, test_name, pytest_html)

        report.extras = extras


def _add_all_svg_files_to_report(
    extras: list, output_dirs: list, test_name: str, pytest_html
) -> None:
    """Add SVGs from multiple output directories to HTML report with single header."""
    if not pytest_html:
        return

    # Collect all SVG files from all directories
    all_svg_files = []
    for output_dir in output_dirs:
        svg_files = list(output_dir.glob("*.svg"))
        for svg_file in svg_files:
            all_svg_files.append((svg_file, output_dir))

    if not all_svg_files:
        return

    # Add a single header for this test's outputs
    header_html = (
        f'<div class="report-header">'
        f"<strong>Generated SVGs for {test_name}:</strong></div>"
    )
    extras.append(pytest_html.extras.html(header_html))

    # Create a flex container for side-by-side SVG display
    svg_items_html = []

    # Process each SVG file
    for svg_file, source_dir in sorted(all_svg_files, key=lambda x: x[0].name):
        try:
            # Read SVG content
            svg_content = svg_file.read_text(encoding="utf-8")

            # Shrink to content bounds and prepare for HTML display
            display_svg_content = _shrink_svg_to_content(svg_content)

            # Create individual SVG item with source directory info
            svg_item = (
                f'<div class="svg-item-container">'
                f'<div class="svg-item-title">📄 {svg_file.name}</div>'
                f'<div class="svg-item-content">{display_svg_content}</div>'
                f'<div class="svg-item-info">'
                f"Size: {svg_file.stat().st_size:,} bytes<br>"
                f"From: {source_dir.name}</div>"
                f"</div>"
            )
            svg_items_html.append(svg_item)

        except Exception as e:
            # If we can't read the SVG, add an error item
            error_item = (
                f'<div class="error-item-container">'
                f'<div class="error-item-title">'
                f"❌ Could not display {svg_file.name}</div>"
                f'<div class="svg-item-info">Error: {e}</div>'
                f"</div>"
            )
            svg_items_html.append(error_item)

    # Add the flex container with all SVG items
    if svg_items_html:
        flex_container = (
            f'<div class="svg-flex-container">{" ".join(svg_items_html)}</div>'
        )
        extras.append(pytest_html.extras.html(flex_container))


def _shrink_svg_to_content(svg_content: str, margin: int = 1) -> str:
    """Shrink SVG to content bounds using svgpathtools."""
    if svgpathtools is None:
        # svgpathtools not available, return SVG with basic styling
        converted_content = re.sub(
            r"<svg([^>]*)>",
            r'<svg\1 style="width: 100%; height: auto; display: block;">',
            svg_content,
        )
        return converted_content

    # Parse SVG content
    root = ET.fromstring(svg_content)

    # Get all paths from the SVG
    paths = svgpathtools.document.flattened_paths(root)

    if not paths:
        # No paths found, return cleaned SVG without bbox modification
        converted_content = svg_content
        # Add CSS styling
        converted_content = re.sub(
            r"<svg([^>]*)>",
            r'<svg\1 style="width: 100%; height: auto; display: block;">',
            converted_content,
        )
        return converted_content

    # Calculate bounding box
    bbox = paths[0].bbox()
    for path in paths[1:]:
        path_bbox = path.bbox()
        bbox = (
            min(bbox[0], path_bbox[0]),  # min_x
            max(bbox[1], path_bbox[1]),  # max_x
            min(bbox[2], path_bbox[2]),  # min_y
            max(bbox[3], path_bbox[3]),  # max_y
        )

    # Add margin
    bbox = (
        bbox[0] - margin,
        bbox[1] + margin,
        bbox[2] - margin,
        bbox[3] + margin,
    )

    # Update SVG attributes
    width = bbox[1] - bbox[0]
    height = bbox[3] - bbox[2]

    # Scale factor for HTML display
    scale_factor = 4
    display_width = width * scale_factor / 10  # Convert mm to cm and scale
    display_height = height * scale_factor / 10

    # Update root element
    root.set("viewBox", f"{bbox[0]} {bbox[2]} {width} {height}")
    root.set("width", f"{display_width:.3f}cm")
    root.set("height", f"{display_height:.3f}cm")

    # Add CSS styling
    root.set("style", "width: 100%; height: auto; display: block;")

    # Convert back to string and clean up
    converted_content = ET.tostring(root, encoding="unicode")
    return converted_content


def _add_cli_outputs_to_report(
    extras: list, cli_outputs: list, test_name: str, pytest_html
) -> None:
    """Add CLI command outputs to HTML report extras."""
    if not pytest_html or not cli_outputs:
        return

    # Add a header for CLI outputs
    header_html = (
        f'<div class="report-header">'
        f"<strong>CLI Commands and Outputs for {test_name}:</strong></div>"
    )
    extras.append(pytest_html.extras.html(header_html))

    for i, output_info in enumerate(cli_outputs, 1):
        command = output_info.get("command", "Unknown command")
        stdout = output_info.get("stdout", "")
        stderr = output_info.get("stderr", "")
        returncode = output_info.get("returncode", "Unknown")

        # Determine status class
        status_class = "cli-status-success" if returncode == 0 else "cli-status-failed"
        container_class = (
            "cli-output-container" if returncode == 0 else "cli-output-container failed"
        )
        status_text = "✓ SUCCESS" if returncode == 0 else "✗ FAILED"

        cli_html = (
            f'<div class="{container_class}">'
            '<div class="cli-output-header">'
            f"<strong>Command #{i}</strong>"
            f'<span class="{status_class}">{status_text} (exit code: {returncode})'
            "</span></div>"
            f'<div class="cli-command"><code>{command}</code></div>'
            '<div class="cli-output-grid">'
            '<div><strong>STDOUT:</strong><pre class="cli-output-pre">'
            f'{stdout or "(no output)"}</pre></div>'
            '<div><strong>STDERR:</strong><pre class="cli-output-pre">'
            f'{stderr or "(no output)"}</pre></div>'
            "</div></div>"
        )

        extras.append(pytest_html.extras.html(cli_html))


@pytest.fixture
def generate_references(request):
    """Check if --generate-references flag is set."""
    return request.config.getoption("--generate-references")


@pytest.fixture
def capture_outputs(request, reference_dir, generate_references):
    """Fixture to capture output directories and CLI outputs for HTML reporting."""
    output_dirs = []
    cli_outputs = []

    def add_output_dir(path: Path):
        """Register an output directory to be captured in HTML report."""
        output_dirs.append(str(path))
        # Store on the current test item for the hook to find
        request.node._pytest_html_capture = output_dirs

    # Initialize CLI outputs on the request node so cli_runner can find it
    request.node._pytest_html_cli_outputs = cli_outputs

    def copy_to_references(test_name: str, pcb_file_name: str):
        """Copy generated SVGs to reference directory if flag is set."""
        if not generate_references:
            return

        # Create reference subdirectory for this PCB file
        pcb_ref_dir = reference_dir / pcb_file_name
        pcb_ref_dir.mkdir(parents=True, exist_ok=True)

        # Copy all SVG files from output directories
        copied_files = []
        for output_dir_str in output_dirs:
            output_dir = Path(output_dir_str)
            if output_dir.exists():
                svg_files = list(output_dir.glob("*.svg"))
                for svg_file in svg_files:
                    # Create reference filename based on test and file name
                    ref_filename = f"{test_name}_{svg_file.name}"
                    ref_path = pcb_ref_dir / ref_filename

                    shutil.copy2(svg_file, ref_path)
                    copied_files.append(ref_path)

        if copied_files:
            msg = f"\nGenerated {len(copied_files)} reference files in {pcb_ref_dir}"
            print(msg)  # noqa: T201
            for file_path in copied_files:
                print(f"  -> {file_path}")  # noqa: T201

    # Store output dirs and CLI outputs on the fixture for access
    add_output_dir.output_dirs = output_dirs
    add_output_dir.cli_outputs = cli_outputs
    add_output_dir.copy_to_references = copy_to_references
    return add_output_dir
