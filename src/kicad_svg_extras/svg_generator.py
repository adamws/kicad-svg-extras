# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""SVG generation wrapper around kicad-cli."""

import logging
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from kicad_svg_extras import pcb_net_filter
from kicad_svg_extras.colors import DEFAULT_BACKGROUND_DARK, apply_color_to_svg

logger = logging.getLogger(__name__)

# SVG namespace
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def run_kicad_cli_svg(pcb_file: Path, layers: str, output_file: Path) -> None:
    """Run kicad-cli to generate SVG."""
    cmd = [
        "kicad-cli",
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


def post_process_svg(svg_file: Path, *, add_background: bool = True) -> None:
    """Post-process SVG to add background and fix units."""
    # Parse SVG
    tree = ET.parse(svg_file)
    root = tree.getroot()

    # Add background only if requested
    if add_background:
        desc = root.find(f".//{{{SVG_NS}}}desc")
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


def generate_color_grouped_svgs(
    pcb_file: Path,
    side: str,
    output_dir: Path,
    net_colors: dict[str, str],
    *,
    keep_pcb: bool = False,
    skip_zones: bool = False,
) -> dict[str, Path]:
    """Generate SVGs grouped by color for optimization."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load board and net codes once for efficiency
    board = pcb_net_filter.load_board(pcb_file)
    net_codes = pcb_net_filter.get_net_codes(board)

    # Group nets by their final colors
    color_groups: dict[str, list[str]] = {}
    default_nets = []

    net_names = list(net_codes.keys())

    for net_name in net_names:
        # Skip nets with no elements on this side
        if not pcb_net_filter.has_elements_on_side(
            board, net_name or "<no_net>", side, net_codes
        ):
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
        temp_pcb = pcb_net_filter.create_multi_net_pcb(
            pcb_file, default_nets, skip_zones=skip_zones
        )

        try:
            # Use only copper layer for side-specific SVGs
            # to avoid cross-contamination
            layers = "F.Cu" if side == "front" else "B.Cu"
            run_kicad_cli_svg(temp_pcb, layers, default_svg)
            post_process_svg(default_svg, add_background=False)

            # Map all default nets to the same SVG file
            for net_name in default_nets:
                net_svgs[net_name] = default_svg

        except Exception as e:
            logger.warning(f"Failed to generate SVG for default nets: {e}")
        finally:
            if not keep_pcb and temp_pcb.exists():
                temp_pcb.unlink()

    # Generate one SVG per color group and apply color immediately
    for color, nets_with_color in color_groups.items():
        logger.info(f"Processing {len(nets_with_color)} nets with color {color}...")
        # Create safe filename from color hex
        safe_color = color.replace("#", "color_").replace("/", "_").replace("\\", "_")
        raw_svg = output_dir / f"raw_{safe_color}_{side}.svg"
        color_svg = output_dir / f"{safe_color}_{side}.svg"
        temp_pcb = pcb_net_filter.create_multi_net_pcb(
            pcb_file, nets_with_color, skip_zones=skip_zones
        )

        try:
            # Use only copper layer for side-specific SVGs
            # to avoid cross-contamination
            layers = "F.Cu" if side == "front" else "B.Cu"
            run_kicad_cli_svg(temp_pcb, layers, raw_svg)
            post_process_svg(raw_svg, add_background=False)

            # Apply color to the intermediate SVG immediately
            apply_color_to_svg(raw_svg, color, color_svg)

            # Clean up raw SVG if not keeping intermediates
            if not keep_pcb and raw_svg.exists():
                raw_svg.unlink()

            # Map all nets with this color to the same colored SVG file
            for net_name in nets_with_color:
                net_svgs[net_name] = color_svg

        except Exception as e:
            msg = f"Failed to generate SVG for color {color}: {e}"
            logger.warning(msg)
        finally:
            if not keep_pcb and temp_pcb.exists():
                temp_pcb.unlink()

    return net_svgs


def generate_edge_cuts_svg(pcb_file: Path, output_file: Path) -> Path:
    """Generate SVG for board edge cuts."""
    layers = "Edge.Cuts"
    run_kicad_cli_svg(pcb_file, layers, output_file)
    post_process_svg(output_file, add_background=False)
    return output_file


def generate_silkscreen_svg(pcb_file: Path, side: str, output_file: Path) -> Path:
    """Generate SVG for silkscreen layer."""
    if side == "front":
        layers = "F.Silkscreen"
    elif side == "back":
        layers = "B.Silkscreen"
    else:
        msg = f"Invalid side: {side}. Must be 'front' or 'back'"
        raise ValueError(msg)

    run_kicad_cli_svg(pcb_file, layers, output_file)
    post_process_svg(output_file, add_background=False)
    return output_file


def get_net_names(pcb_file: Path) -> list[str]:
    """Get all net names from the PCB."""
    net_names = pcb_net_filter.get_net_names(pcb_file)
    return [name for name in net_names if name]  # Filter out empty names
