# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""SVG generation wrapper around kicad-cli."""

import logging
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from kicad_svg_extras.colors import DEFAULT_BACKGROUND_DARK, apply_color_to_svg
from kicad_svg_extras.pcb_net_filter import PCBNetFilter

logger = logging.getLogger(__name__)


class SVGGenerator:
    """Generate SVGs with per-net coloring using kicad-cli."""

    def __init__(
        self,
        pcb_file: Path,
        *,
        skip_zones: bool = False,
        kicad_cli_cmd: str = "kicad-cli",
    ):
        self.pcb_file = pcb_file
        self.net_filter = PCBNetFilter(pcb_file, skip_zones=skip_zones)
        self.skip_zones = skip_zones
        self.kicad_cli_cmd = kicad_cli_cmd

        # Default layers for front and back
        self.front_layers = "B.Cu,F.Cu,F.Silkscreen,Edge.Cuts"
        self.back_layers = "F.Cu,B.Cu,B.Silkscreen,Edge.Cuts"

        # SVG namespace
        self.svg_ns = "http://www.w3.org/2000/svg"
        ET.register_namespace("", self.svg_ns)

    def set_layers(self, front_layers: str, back_layers: str) -> None:
        """Set custom layer specifications."""
        self.front_layers = front_layers
        self.back_layers = back_layers

    def _run_kicad_cli_svg(
        self, pcb_file: Path, layers: str, output_file: Path
    ) -> None:
        """Run kicad-cli to generate SVG."""
        cmd = [
            self.kicad_cli_cmd,
            "pcb",
            "export",
            "svg",
            "--exclude-drawing-sheet",
            "--page-size-mode",
            "0",  # Use PCB boundary for consistent coordinate system
            "-l",
            layers,
            "-o",
            str(output_file),
            str(pcb_file),
        ]

        result = subprocess.run(  # noqa: S603
            cmd, check=False, capture_output=True, text=True
        )
        if result.returncode != 0:
            msg = f"kicad-cli failed: {result.stderr}"
            raise RuntimeError(msg)

    def _post_process_svg(self, svg_file: Path, *, add_background: bool = True) -> None:
        """Post-process SVG to add background and fix units."""
        # Parse SVG
        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Add background only if requested
        if add_background:
            desc = root.find(f".//{{{self.svg_ns}}}desc")
            if desc is not None:
                svg_w = root.attrib.get("width", "")
                svg_h = root.attrib.get("height", "")

                parent = root
                children = list(parent)
                desc_index = children.index(desc)

                # Add dark background
                rect = ET.Element(
                    "rect",
                    x="0",
                    y="0",
                    width=svg_w,
                    height=svg_h,
                    fill=DEFAULT_BACKGROUND_DARK,
                )
                parent.insert(desc_index + 1, rect)

                tree.write(svg_file, encoding="unicode")

        # Fix units (mm to cm)
        with open(svg_file) as f:
            content = f.read()

        content = content.replace('mm"', 'cm"')

        with open(svg_file, "w") as f:
            f.write(content)

    def generate_standard_svg(self, side: str, output_file: Path) -> None:
        """Generate standard SVG for front or back side."""
        layers = self.front_layers if side == "front" else self.back_layers
        self._run_kicad_cli_svg(self.pcb_file, layers, output_file)
        self._post_process_svg(output_file)

    def generate_net_svg(
        self,
        net_name: str,
        side: str,
        output_file: Optional[Path] = None,
        *,
        keep_pcb: bool = False,
    ) -> Path:
        """Generate SVG for a specific net."""
        if output_file is None:
            fd, temp_path = tempfile.mkstemp(suffix=".svg")
            os.close(fd)
            output_file = Path(temp_path)

        # Create temporary PCB with only this net
        if keep_pcb:
            # Save to output directory with descriptive name
            safe_name = net_name.replace("/", "_").replace("\\", "_")
            temp_pcb = output_file.parent / f"{safe_name}_{side}.kicad_pcb"
        else:
            temp_pcb = self.net_filter.create_single_net_pcb(net_name)

        temp_pcb = self.net_filter.create_single_net_pcb(net_name, temp_pcb)

        try:
            # For intermediate files, use only copper layers
            if keep_pcb:
                layers = "F.Cu" if side == "front" else "B.Cu"
            else:
                layers = self.front_layers if side == "front" else self.back_layers

            self._run_kicad_cli_svg(temp_pcb, layers, output_file)
            # Don't add background to intermediate SVGs
            self._post_process_svg(output_file, add_background=False)
        finally:
            # Clean up temporary PCB only if not keeping it
            if not keep_pcb and temp_pcb.exists():
                temp_pcb.unlink()

        return output_file

    def generate_all_net_svgs(
        self, side: str, output_dir: Path, *, keep_pcb: bool = False
    ) -> dict[str, Path]:
        """Generate SVGs for all nets."""
        output_dir.mkdir(parents=True, exist_ok=True)

        net_svgs = {}
        net_names = self.net_filter.get_net_names()

        for net_name in net_names:
            # Create safe filename
            if net_name:
                safe_name = net_name.replace("/", "_").replace("\\", "_")
            else:
                safe_name = "<no_net>"
            output_file = output_dir / f"{safe_name}_{side}.svg"

            # Skip nets with no elements on this side
            if not self.net_filter.has_elements_on_side(net_name or "<no_net>", side):
                logger.info(
                    "Skipping net '%s' on %s side (no elements found)",
                    net_name or "<no_net>",
                    side,
                )
                continue

            try:
                self.generate_net_svg(net_name, side, output_file, keep_pcb=keep_pcb)
                net_svgs[net_name] = output_file
            except Exception as e:
                logger.warning(
                    f"Warning: Failed to generate SVG for net '{net_name}': {e}"
                )
                continue

        return net_svgs

    def generate_color_grouped_svgs(
        self,
        side: str,
        output_dir: Path,
        net_colors: dict[str, str],
        *,
        keep_pcb: bool = False,
    ) -> dict[str, Path]:
        """Generate SVGs grouped by color for optimization."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Group nets by their final colors
        color_groups: dict[str, list[str]] = {}
        default_nets = []

        net_names = self.net_filter.get_net_names()

        for net_name in net_names:
            # Skip nets with no elements on this side
            if not self.net_filter.has_elements_on_side(net_name or "<no_net>", side):
                continue

            if net_name in net_colors:
                color = net_colors[net_name]
                if color not in color_groups:
                    color_groups[color] = []
                color_groups[color].append(net_name)
            else:
                default_nets.append(net_name)

        net_svgs = {}

        # Generate one SVG for all nets with default KiCad colors
        if default_nets:
            logger.info(f"Processing {len(default_nets)} nets with default colors...")
            default_svg = output_dir / f"default_nets_{side}.svg"
            temp_pcb = self.net_filter.create_multi_net_pcb(default_nets)

            try:
                # Use only copper layer for side-specific SVGs
                # to avoid cross-contamination
                layers = "F.Cu" if side == "front" else "B.Cu"
                self._run_kicad_cli_svg(temp_pcb, layers, default_svg)
                self._post_process_svg(default_svg, add_background=False)

                # Map all default nets to the same SVG file
                for net_name in default_nets:
                    net_svgs[net_name] = default_svg

            except Exception as e:
                logger.warning(f"Warning: Failed to generate SVG for default nets: {e}")
            finally:
                if not keep_pcb and temp_pcb.exists():
                    temp_pcb.unlink()

        # Generate one SVG per color group and apply color immediately
        for color, nets_with_color in color_groups.items():
            logger.info(f"Processing {len(nets_with_color)} nets with color {color}...")
            # Create safe filename from color hex
            safe_color = (
                color.replace("#", "color_").replace("/", "_").replace("\\", "_")
            )
            raw_svg = output_dir / f"raw_{safe_color}_{side}.svg"
            color_svg = output_dir / f"{safe_color}_{side}.svg"
            temp_pcb = self.net_filter.create_multi_net_pcb(nets_with_color)

            try:
                # Use only copper layer for side-specific SVGs
                # to avoid cross-contamination
                layers = "F.Cu" if side == "front" else "B.Cu"
                self._run_kicad_cli_svg(temp_pcb, layers, raw_svg)
                self._post_process_svg(raw_svg, add_background=False)

                # Apply color to the intermediate SVG immediately
                apply_color_to_svg(raw_svg, color, color_svg)

                # Clean up raw SVG if not keeping intermediates
                if not keep_pcb and raw_svg.exists():
                    raw_svg.unlink()

                # Map all nets with this color to the same colored SVG file
                for net_name in nets_with_color:
                    net_svgs[net_name] = color_svg

            except Exception as e:
                msg = f"Warning: Failed to generate SVG for color {color}: {e}"
                logger.warning(msg)
            finally:
                if not keep_pcb and temp_pcb.exists():
                    temp_pcb.unlink()

        return net_svgs

    def generate_edge_cuts_svg(self, output_file: Path) -> Path:
        """Generate SVG for board edge cuts."""
        layers = "Edge.Cuts"
        self._run_kicad_cli_svg(self.pcb_file, layers, output_file)
        self._post_process_svg(output_file, add_background=False)
        return output_file

    def generate_silkscreen_svg(self, side: str, output_file: Path) -> Path:
        """Generate SVG for silkscreen layer."""
        if side == "front":
            layers = "F.Silkscreen"
        elif side == "back":
            layers = "B.Silkscreen"
        else:
            msg = f"Invalid side: {side}. Must be 'front' or 'back'"
            raise ValueError(msg)

        self._run_kicad_cli_svg(self.pcb_file, layers, output_file)
        self._post_process_svg(output_file, add_background=False)
        return output_file

    def get_net_names(self) -> list[str]:
        """Get all net names from the PCB."""
        return [
            name for name in self.net_filter.get_net_names() if name
        ]  # Filter out empty names
