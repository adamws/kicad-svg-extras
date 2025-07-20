# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""SVG generation wrapper around kicad-cli."""

import logging
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from kicad_svg_extras import pcb_net_filter
from kicad_svg_extras.colors import (
    apply_color_to_svg,
    apply_css_class_to_svg,
    find_copper_color_in_svg,
)
from kicad_svg_extras.layers import get_copper_layers, sort_layers_by_stackup

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


def generate_color_grouped_svgs(
    pcb_file: Path,
    layers: list[str],
    output_dir: Path,
    net_colors: dict[str, str],
    *,
    keep_pcb: bool = False,
    skip_zones: bool = False,
    use_css_classes: bool = False,
    reverse_stackup: bool = False,
) -> dict[str, Path]:
    """Generate SVGs grouped by color for optimization, or individual SVGs for CSS."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load board and net codes once for efficiency
    board = pcb_net_filter.load_board(pcb_file)
    net_codes = pcb_net_filter.get_net_codes(board)

    net_names = list(net_codes.keys())

    # Filter nets that have elements on any of the specified copper layers
    copper_layers = get_copper_layers(layers)

    active_nets = []
    for net_name in net_names:
        if pcb_net_filter.has_elements_on_layers(
            board, net_name or "<no_net>", copper_layers, net_codes
        ):
            active_nets.append(net_name)

    if use_css_classes:
        # Generate individual SVG per net for CSS styling
        return _generate_individual_net_svgs_per_layer(
            pcb_file,
            copper_layers,
            output_dir,
            active_nets,
            net_colors,
            keep_pcb=keep_pcb,
            skip_zones=skip_zones,
        )
    else:
        # Color grouping approach - process each layer separately then merge
        return _generate_grouped_net_svgs_per_layer(
            pcb_file,
            copper_layers,
            output_dir,
            active_nets,
            net_colors,
            keep_pcb=keep_pcb,
            skip_zones=skip_zones,
            reverse_stackup=reverse_stackup,
        )


def _generate_individual_net_svgs_per_layer(
    pcb_file: Path,
    copper_layers: list[str],
    output_dir: Path,
    active_nets: list[str],
    net_colors: dict[str, str],
    *,
    keep_pcb: bool,
    skip_zones: bool,
) -> dict[str, Path]:
    """Generate individual SVG per net with CSS classes, processing each layer."""
    # Sort layers by stackup order for proper merging
    sorted_copper_layers = sort_layers_by_stackup(copper_layers)

    # Generate individual net SVGs for each layer separately
    layer_svgs: list[Path] = []
    for layer_name in sorted_copper_layers:
        layer_net_svgs = _generate_individual_net_svgs_single_layer(
            pcb_file,
            layer_name,
            output_dir,
            active_nets,
            net_colors,
            keep_pcb=keep_pcb,
            skip_zones=skip_zones,
        )
        # Collect SVGs for this layer
        layer_svgs.extend(layer_net_svgs.values())

    # Return a mapping from nets to SVGs (simplified for interface compatibility)
    net_svgs = {}
    for i, net_name in enumerate(active_nets):
        if i < len(layer_svgs):
            net_svgs[net_name] = layer_svgs[i]

    return net_svgs


def _generate_individual_net_svgs_single_layer(
    pcb_file: Path,
    layer_name: str,
    output_dir: Path,
    active_nets: list[str],
    net_colors: dict[str, str],
    *,
    keep_pcb: bool,
    skip_zones: bool,
) -> dict[str, Path]:
    """Generate individual SVG per net with CSS classes for a single layer."""
    net_svgs = {}

    for net_name in active_nets:
        # Get user-defined color for this net (if any) for CSS class definition
        net_color = net_colors.get(net_name)

        # Create safe filename from net name
        safe_net_name = (net_name or "no_net").replace("/", "_").replace("\\", "_")
        safe_net_name = (
            safe_net_name.replace("(", "_").replace(")", "_").replace(" ", "_")
        )
        safe_net_name = (
            safe_net_name.replace("<", "_").replace(">", "_").replace(":", "_")
        )

        # Create safe layer string for filename
        layer_suffix = layer_name.replace(".", "_")
        raw_svg = output_dir / f"net_{safe_net_name}_{layer_suffix}.svg"
        final_svg = output_dir / f"net_{safe_net_name}_{layer_suffix}_styled.svg"

        # Create PCB with only this net in output directory
        pcb_file_path = output_dir / f"net_{safe_net_name}_{layer_suffix}.kicad_pcb"
        temp_pcb = pcb_net_filter.create_multi_net_pcb(
            pcb_file, [net_name], pcb_file_path, skip_zones=skip_zones
        )

        try:
            # Generate SVG for this net only on this layer
            run_kicad_cli_svg(temp_pcb, layer_name, raw_svg)

            # Apply CSS class styling
            if net_color:
                # User defined a custom color for this net
                apply_css_class_to_svg(raw_svg, net_name, net_color, final_svg)
            else:
                # No custom color defined - detect color from SVG and use that
                detected_color = find_copper_color_in_svg(raw_svg)
                if detected_color:
                    apply_css_class_to_svg(raw_svg, net_name, detected_color, final_svg)
                else:
                    # No color detected, just copy the file without CSS processing
                    shutil.copy2(raw_svg, final_svg)

            # Clean up raw SVG if not keeping intermediates
            if not keep_pcb and raw_svg.exists():
                raw_svg.unlink()

            net_svgs[net_name] = final_svg

        except Exception as e:
            logger.warning(f"Failed to generate SVG for net '{net_name}': {e}")
        finally:
            if not keep_pcb and temp_pcb.exists():
                temp_pcb.unlink()

    return net_svgs


def _generate_grouped_net_svgs_per_layer(
    pcb_file: Path,
    copper_layers: list[str],
    output_dir: Path,
    active_nets: list[str],
    net_colors: dict[str, str],
    *,
    keep_pcb: bool,
    skip_zones: bool,
    reverse_stackup: bool = False,
) -> dict[str, Path]:
    """Generate SVGs grouped by color, processing each layer separately then merging."""
    # Sort layers by stackup order for proper merging
    sorted_copper_layers = sort_layers_by_stackup(
        copper_layers, reverse=reverse_stackup
    )

    # Generate colored SVGs for each layer separately
    all_layer_svgs = []
    for layer_name in sorted_copper_layers:
        layer_net_svgs = _generate_grouped_net_svgs_single_layer(
            pcb_file,
            layer_name,
            output_dir,
            active_nets,
            net_colors,
            keep_pcb=keep_pcb,
            skip_zones=skip_zones,
        )
        # Collect unique SVGs for this layer (in order)
        unique_layer_svgs = list(set(layer_net_svgs.values()))
        all_layer_svgs.extend(unique_layer_svgs)

    # Return a net mapping that includes all generated SVGs
    # We need to create a fake mapping that when processed with set() gives us all SVGs
    net_svgs = {}
    for i, svg in enumerate(all_layer_svgs):
        # Create unique fake net names to ensure all SVGs are included
        fake_net_name = f"__layer_svg_{i}__"
        net_svgs[fake_net_name] = svg

    # Also map some real nets to ensure the interface works
    if active_nets and all_layer_svgs:
        net_svgs[active_nets[0]] = all_layer_svgs[0]

    return net_svgs


def _generate_grouped_net_svgs_single_layer(
    pcb_file: Path,
    layer_name: str,
    output_dir: Path,
    active_nets: list[str],
    net_colors: dict[str, str],
    *,
    keep_pcb: bool,
    skip_zones: bool,
) -> dict[str, Path]:
    """Generate SVGs grouped by color for a single layer (original approach)."""
    # Group nets by their final colors
    color_groups: dict[str, list[str]] = {}
    default_nets = []

    for net_name in active_nets:
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
        logger.info(
            f"Processing {len(default_nets)} nets with default colors on "
            f"{layer_name}..."
        )
        layer_suffix = layer_name.replace(".", "_")
        default_svg = output_dir / f"default_nets_{layer_suffix}.svg"
        pcb_file_path = output_dir / f"default_nets_{layer_suffix}.kicad_pcb"
        temp_pcb = pcb_net_filter.create_multi_net_pcb(
            pcb_file, default_nets, pcb_file_path, skip_zones=skip_zones
        )

        try:
            # Use single layer only
            run_kicad_cli_svg(temp_pcb, layer_name, default_svg)

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
        logger.info(
            f"Processing {len(nets_with_color)} nets with color {color} on "
            f"{layer_name}..."
        )
        # Create safe filename from color hex
        safe_color = color.replace("#", "color_").replace("/", "_").replace("\\", "_")
        layer_suffix = layer_name.replace(".", "_")
        raw_svg = output_dir / f"raw_{safe_color}_{layer_suffix}.svg"
        color_svg = output_dir / f"{safe_color}_{layer_suffix}.svg"
        pcb_file_path = output_dir / f"{safe_color}_{layer_suffix}.kicad_pcb"
        temp_pcb = pcb_net_filter.create_multi_net_pcb(
            pcb_file, nets_with_color, pcb_file_path, skip_zones=skip_zones
        )

        try:
            # Use single layer only
            run_kicad_cli_svg(temp_pcb, layer_name, raw_svg)

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


def generate_layer_svg(pcb_file: Path, layer_name: str, output_file: Path) -> Path:
    """Generate SVG for a specific layer.

    Args:
        pcb_file: Path to PCB file
        layer_name: KiCad layer name (e.g., "Edge.Cuts", "F.SilkS", etc.)
        output_file: Output SVG file path

    Returns:
        Path to the generated SVG file
    """
    run_kicad_cli_svg(pcb_file, layer_name, output_file)
    return output_file


def generate_edge_cuts_svg(pcb_file: Path, output_file: Path) -> Path:
    """Generate SVG for board edge cuts."""
    return generate_layer_svg(pcb_file, "Edge.Cuts", output_file)


def generate_silkscreen_svg(pcb_file: Path, side: str, output_file: Path) -> Path:
    """Generate SVG for silkscreen layer."""
    if side == "front":
        layer_name = "F.SilkS"
    elif side == "back":
        layer_name = "B.SilkS"
    else:
        msg = f"Invalid side: {side}. Must be 'front' or 'back'"
        raise ValueError(msg)

    return generate_layer_svg(pcb_file, layer_name, output_file)


def get_net_names(pcb_file: Path) -> list[str]:
    """Get all net names from the PCB."""
    net_names = pcb_net_filter.get_net_names(pcb_file)
    return [name for name in net_names if name]  # Filter out empty names
