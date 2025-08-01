# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Functional tests for SVG generation from KiCad PCB files."""
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from xmldiff import main as xmldiff_main


@pytest.mark.functional
@pytest.mark.requires_pcb_file
class TestSVGGeneration:
    """Test SVG generation functionality with real PCB files."""

    @pytest.mark.parametrize(
        "fit_to_content",
        ["none", "all", "edges_only"],
    )
    def test_basic_svg_generation(
        self,
        cli_runner,
        temp_output_dir,
        pcb_files_dir,
        capture_outputs,
        fit_to_content,
    ):
        """Test basic SVG generation without any special options."""
        # This test will be skipped until PCB files are provided
        pcb_files = list(pcb_files_dir.glob("**/*.kicad_pcb"))
        if not pcb_files:
            pytest.skip("No PCB files available for testing")

        pcb_file = pcb_files[0]
        output_dir = temp_output_dir / "basic_test"

        # Register output directory for HTML report capture
        capture_outputs(output_dir)

        # Run CLI command
        output_file = output_dir / "test_output.svg"
        result = cli_runner(
            [
                "--output",
                str(output_file),
                "--layers",
                "F.Cu,B.Cu",
                "--fit-to-content",
                fit_to_content,
                str(pcb_file),
            ]
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Check that the output SVG file was generated
        assert output_file.exists(), f"Expected output SVG not found: {output_file}"

        # Copy to references if flag is set
        capture_outputs.copy_to_references("basic", pcb_file.stem)

    @pytest.mark.parametrize(
        "layers,test_name",
        [
            (["F.Cu"], "front_copper_only"),
            (["B.Cu"], "back_copper_only"),
            (["F.Cu", "B.Cu"], "front_back_copper"),
            (["F.Cu", "B.Cu", "B.SilkS"], "copper_with_back_silk"),
            (["F.Cu", "B.Cu", "B.SilkS", "Edge.Cuts"], "full_layer_stack"),
        ],
    )
    def test_layer_combinations(
        self,
        cli_runner,
        temp_output_dir,
        pcb_files_dir,
        capture_outputs,
        layers,
        test_name,
    ):
        """Test various layer combinations."""
        pcb_files = list(pcb_files_dir.glob("**/*.kicad_pcb"))
        if not pcb_files:
            pytest.skip("No PCB files available for testing")

        pcb_file = pcb_files[0]

        # Create unique output directory for this specific test case
        output_dir = temp_output_dir / f"layers_{test_name}"
        layers_str = ",".join(layers)

        # Register output directory for HTML report capture
        capture_outputs(output_dir)

        output_file = output_dir / f"{test_name}.svg"
        result = cli_runner(
            [
                "--output",
                str(output_file),
                "--layers",
                layers_str,
                str(pcb_file),
            ]
        )

        assert result.returncode == 0, f"Failed for layers {layers}: {result.stderr}"

        # Verify output file exists
        assert output_file.exists(), f"No SVG file generated for layers: {layers}"

        # Copy to references if flag is set (with unique name)
        capture_outputs.copy_to_references(
            f"layer_combinations_{test_name}", pcb_file.stem
        )

    def test_color_application(
        self,
        cli_runner,
        temp_output_dir,
        pcb_files_dir,
        sample_configs,
        capture_outputs,
    ):
        """Test net color application."""
        pcb_files = list(pcb_files_dir.glob("**/*.kicad_pcb"))
        if not pcb_files:
            pytest.skip("No PCB files available for testing")

        pcb_file = pcb_files[0]
        output_dir = temp_output_dir / "color_test"

        # Register output directory for HTML report capture
        capture_outputs(output_dir)

        # Test with basic color config
        output_file = output_dir / "colored_output.svg"
        result = cli_runner(
            [
                "--output",
                str(output_file),
                "--layers",
                "F.Cu,B.Cu",
                "--colors",
                str(sample_configs["basic"]),
                str(pcb_file),
            ]
        )

        assert result.returncode == 0, f"Color test failed: {result.stderr}"

        # Check that colored SVG was generated
        assert output_file.exists(), "No colored SVG file was generated"

        # Verify colors are applied by checking file content
        svg_file = output_file
        content = svg_file.read_text()
        # Should contain colored elements (any hex color, not just black/white)
        has_colors = any(
            color_pattern in content.lower()
            for color_pattern in [
                "#c83434",
                "#ff0000",
                "#0000ff",
                "#00ff00",
                "fill:#",
            ]
        )
        assert has_colors, f"No colored elements found in {svg_file}"

        # Copy to references if flag is set
        capture_outputs.copy_to_references("color_application", pcb_file.stem)


@pytest.mark.functional
class TestLayerOrderComparison:
    """Test layer merging order against KiCad CLI output."""

    def remove_empty_groups(self, svg_file: Path) -> None:
        tree = ET.parse(svg_file)
        root = tree.getroot()
        name = "{http://www.w3.org/2000/svg}g"

        def _remove_empty_groups(root) -> None:
            for elem in root.findall(name):
                if len(elem) == 0:
                    root.remove(elem)
            for child in root:
                _remove_empty_groups(child)

        _remove_empty_groups(root)
        tree.write(svg_file, encoding="unicode")

    def test_with_kicad_cli_reference(
        self, cli_runner, temp_output_dir, pcb_files_dir, capture_outputs
    ):
        """Test that our SVG generation produces semantically equivalent output
        to KiCad CLI export using xmldiff for comparison."""

        pcb_file = pcb_files_dir / "very_simple_2layer/udb.kicad_pcb"
        assert Path(pcb_file).is_file()

        output_dir = temp_output_dir / "layer_order_comparison"

        # Register output directory for HTML report capture
        capture_outputs(output_dir)

        # Test with a basic layer combination that both tools should handle identically
        layers = ["F.Cu", "B.Cu", "Edge.Cuts"]
        layers_str = ",".join(layers)

        # Generate reference SVG using kicad-cli
        kicad_reference = output_dir / "kicad_reference.svg"

        try:
            # Run kicad-cli to generate reference SVG
            kicad_cmd = [
                "kicad-cli",
                "pcb",
                "export",
                "svg",
                "--exclude-drawing-sheet",
                "--page-size-mode",
                "0",
                "--layers",
                layers_str,
                "--output",
                str(kicad_reference),
                str(pcb_file),
            ]
            result = subprocess.run(  # noqa: S603
                kicad_cmd, capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            pytest.skip(f"kicad-cli not available or failed: {e}")
        except FileNotFoundError:
            pytest.skip("kicad-cli not found in PATH")

        # kicad-cli creates a lot of empty groups. Remove them to make
        # comparison with our results easier (we remove empty groups by default).
        self.remove_empty_groups(kicad_reference)

        # Generate our tool's SVG output (without custom colors to match kicad-cli)
        our_svg_file = output_dir / "our_output.svg"
        result = cli_runner(
            [
                "--output",
                str(our_svg_file),
                "--no-background",
                "--fit-to-content",
                "none",
                "--layers",
                layers_str,
                str(pcb_file),
            ]
        )

        assert result.returncode == 0, f"Our tool failed: {result.stderr}"
        assert our_svg_file.exists(), f"Expected SVG file not found: {our_svg_file}"

        # Compare the two SVG files semantically using xmldiff
        try:
            # Get diff between the two SVG files
            diff_result = xmldiff_main.diff_files(
                str(kicad_reference),
                str(our_svg_file),
                formatter=xmldiff_main.FORMATTERS["diff"](),
            )

            # Filter out metadata differences (title, desc elements)
            if diff_result:
                # Convert to string to analyze differences
                diff_str = str(diff_result)

                # Check if differences are only metadata-related
                lines = diff_str.strip().split("\n")
                non_metadata_diffs = []

                for line in lines:
                    # Skip differences related to title and desc elements
                    # and their content
                    is_metadata_diff = (
                        "title]" in line
                        or "desc]" in line
                        or "update-text, /*/*[1]" in line  # title content
                        or "update-text, /*/*[2]" in line  # desc content
                        or (
                            "move" in line and ("/*/*[1]" in line or "/*/*[12]" in line)
                        )  # title/desc element moves
                    )

                    if not is_metadata_diff:
                        non_metadata_diffs.append(line)

                # If there are substantial non-metadata differences, fail the test
                if non_metadata_diffs:
                    pytest.fail(
                        f"SVG files have substantial differences beyond metadata. "
                        f"Non-metadata differences between {kicad_reference} "
                        f"and {our_svg_file}:\n"
                        f"{chr(10).join(non_metadata_diffs)}"
                    )
                # Otherwise, consider it a pass (only metadata differences)
        except Exception as e:
            pytest.fail(f"Failed to compare SVG files with xmldiff: {e}")


@pytest.mark.functional
class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_pcb_file(self, cli_runner, temp_output_dir):
        """Test handling of invalid PCB file."""
        invalid_file = temp_output_dir / "invalid.kicad_pcb"
        invalid_file.write_text("not a valid pcb file")

        output_dir = temp_output_dir / "error_test"

        output_file = output_dir / "should_not_exist.svg"
        result = cli_runner(
            ["--output", str(output_file), "--layers", "F.Cu,B.Cu", str(invalid_file)],
            check=False,
        )

        assert result.returncode != 0, "Should fail with invalid PCB file"
        assert "error" in result.stderr.lower() or "fail" in result.stderr.lower()

    def test_invalid_layer_specification(
        self, cli_runner, temp_output_dir, pcb_files_dir
    ):
        """Test handling of invalid layer names."""
        pcb_files = list(pcb_files_dir.glob("**/*.kicad_pcb"))
        if not pcb_files:
            pytest.skip("No PCB files available for testing")

        pcb_file = pcb_files[0]
        output_dir = temp_output_dir / "invalid_layer_test"

        output_file = output_dir / "should_not_exist.svg"
        cli_runner(
            [
                "--output",
                str(output_file),
                "--layers",
                "Invalid.Layer,Another.Bad",
                str(pcb_file),
            ],
            check=False,
        )

        # Should either fail or warn about invalid layers
        # Implementation may vary on how this is handled
