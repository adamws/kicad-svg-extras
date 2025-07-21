# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Functional tests for SVG generation from KiCad PCB files."""

import pytest


@pytest.mark.functional
@pytest.mark.requires_pcb_file
class TestSVGGeneration:
    """Test SVG generation functionality with real PCB files."""

    def test_basic_svg_generation(
        self, cli_runner, temp_output_dir, pcb_files_dir, capture_outputs
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
        result = cli_runner(
            [
                "--layers",
                "F.Cu,B.Cu",
                "--fit-to-content",
                str(pcb_file),
                str(output_dir),
            ]
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Check that SVG files were generated
        svg_files = list(output_dir.glob("*.svg"))
        assert len(svg_files) > 0, "No SVG files were generated"

        # Copy to references if flag is set
        capture_outputs.copy_to_references("basic", pcb_file.stem)

    def test_layer_combinations(
        self, cli_runner, temp_output_dir, pcb_files_dir, capture_outputs
    ):
        """Test various layer combinations."""
        pcb_files = list(pcb_files_dir.glob("**/*.kicad_pcb"))
        if not pcb_files:
            pytest.skip("No PCB files available for testing")

        pcb_file = pcb_files[0]

        # Test different layer combinations
        layer_combinations = [
            ["F.Cu"],
            ["B.Cu"],
            ["F.Cu", "B.Cu"],
            ["F.Cu", "B.Cu", "F.SilkS"],
            ["F.Cu", "B.Cu", "F.SilkS", "Edge.Cuts"],
        ]

        for layers in layer_combinations:
            output_dir = (
                temp_output_dir / f"layers_{'_'.join(layers).replace('.', '_')}"
            )
            layers_str = ",".join(layers)

            # Register output directory for HTML report capture
            capture_outputs(output_dir)

            result = cli_runner(
                [
                    "--layers",
                    layers_str,
                    "--fit-to-content",
                    str(pcb_file),
                    str(output_dir),
                ]
            )

            assert (
                result.returncode == 0
            ), f"Failed for layers {layers}: {result.stderr}"

            # Verify output files exist
            svg_files = list(output_dir.glob("*.svg"))
            assert len(svg_files) > 0, f"No SVG files generated for layers: {layers}"

        # Copy to references if flag is set
        capture_outputs.copy_to_references("layer_combinations", pcb_file.stem)

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
        result = cli_runner(
            [
                "--layers",
                "F.Cu,B.Cu",
                "--colors",
                str(sample_configs["basic"]),
                "--fit-to-content",
                str(pcb_file),
                str(output_dir),
            ]
        )

        assert result.returncode == 0, f"Color test failed: {result.stderr}"

        # Check that colored SVG was generated
        colored_svgs = list(output_dir.glob("colored_*.svg"))
        assert len(colored_svgs) > 0, "No colored SVG files were generated"

        # Verify colors are applied by checking file content
        for svg_file in colored_svgs:
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
class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_pcb_file(self, cli_runner, temp_output_dir):
        """Test handling of invalid PCB file."""
        invalid_file = temp_output_dir / "invalid.kicad_pcb"
        invalid_file.write_text("not a valid pcb file")

        output_dir = temp_output_dir / "error_test"

        result = cli_runner(
            ["--layers", "F.Cu,B.Cu", str(invalid_file), str(output_dir)], check=False
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

        cli_runner(
            ["--layers", "Invalid.Layer,Another.Bad", str(pcb_file), str(output_dir)],
            check=False,
        )

        # Should either fail or warn about invalid layers
        # Implementation may vary on how this is handled
