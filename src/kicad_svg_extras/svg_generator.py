# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""SVG generation using pcbnew API."""

import logging
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from kicad_svg_extras import pcbnew_utils
from kicad_svg_extras.colors import (
    apply_color_to_svg,
    apply_css_class_to_svg,
    find_copper_color_in_svg,
)
from kicad_svg_extras.layers import get_copper_layers
from kicad_svg_extras.svg_processor import merge_svg_files

logger = logging.getLogger(__name__)

# SVG namespace
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def generate_svg(
    pcb_file: Path,
    layers: str,
    output_file: Path,
    *,
    net_names: Optional[set[str]] = None,
    skip_zones: bool = False,
    skip_through_holes: bool = False,
    keep_pcb: bool = False,
) -> None:
    """Generate SVG

    This function uses the pcbnew PLOT_CONTROLLER API directly to avoid
    subprocess overhead

    Args:
        pcb_file: Path to PCB file
        layers: Comma-separated layer names
        output_file: Output SVG file path
        net_names: Optional set of net names to filter (None = all nets)
        skip_zones: Skip zones in output
        skip_through_holes: Skip through hole pads
        keep_pcb: Keep intermediate PCB files for debugging
    """
    if net_names is not None:
        # Create temporary filtered PCB file for PLOT_CONTROLLER
        temp_pcb = output_file.parent / f"temp_{output_file.stem}.kicad_pcb"
        pcbnew_utils.create_filtered_pcb(
            pcb_file,
            net_names,
            output_file=temp_pcb,
            skip_zones=skip_zones,
        )
        try:
            # Generate SVGs in isolated temp directory
            generated_svgs = pcbnew_utils.generate_svg_from_board(
                temp_pcb,
                layers,
                output_file.parent,
                skip_through_holes=skip_through_holes,
            )

            # Handle file naming - merge multiple layers or rename single layer
            if len(generated_svgs) == 1:
                # Single layer - rename to target output file
                generated_svgs[0].rename(output_file)
            else:
                # Multiple layers - merge them
                merge_svg_files(generated_svgs, output_file)
                # Clean up temporary files
                for temp_file in generated_svgs:
                    if temp_file.exists():
                        temp_file.unlink()
        finally:
            # Clean up temporary files (PCB and associated project files)
            if not keep_pcb:
                if temp_pcb.exists():
                    temp_pcb.unlink()
                # Also clean up project files that KiCad automatically creates
                for ext in [".kicad_prl", ".kicad_pro"]:
                    project_file = temp_pcb.with_suffix(ext)
                    if project_file.exists():
                        project_file.unlink()
    else:
        # No filtering needed, use original PCB file directly
        generated_svgs = pcbnew_utils.generate_svg_from_board(
            pcb_file, layers, output_file.parent, skip_through_holes=skip_through_holes
        )

        # Handle file naming - merge multiple layers or rename single layer
        if len(generated_svgs) == 1:
            # Single layer - rename to target output file
            generated_svgs[0].rename(output_file)
        else:
            # Multiple layers - merge them
            merge_svg_files(generated_svgs, output_file)
            # Clean up temporary files
            for temp_file in generated_svgs:
                if temp_file.exists():
                    temp_file.unlink()


def generate_color_grouped_svgs(
    pcb_file: Path,
    layers: list[str],
    output_dir: Path,
    net_colors: dict[str, str],
    *,
    keep_pcb: bool = False,
    skip_zones: bool = False,
    use_css_classes: bool = False,
) -> dict[str, Path]:
    """Generate SVGs grouped by color for optimization, or individual SVGs for CSS."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load board and net codes once for efficiency
    board = pcbnew_utils.load_board(pcb_file)
    net_codes = pcbnew_utils.get_net_codes(board)

    net_names = list(net_codes.keys())

    # Filter nets that have elements on any of the specified copper layers
    copper_layers = get_copper_layers(layers)

    active_nets = []
    for net_name in net_names:
        if pcbnew_utils.has_elements_on_layers(
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
    # Generate individual net SVGs for each layer separately
    layer_svgs: list[Path] = []
    for layer_name in copper_layers:
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

        # Generate SVG for this net only on this layer using optimized approach
        try:
            generate_svg(
                pcb_file,
                layer_name,
                raw_svg,
                net_names={net_name},
                skip_zones=skip_zones,
                keep_pcb=keep_pcb,
            )

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
) -> dict[str, Path]:
    """Generate SVGs grouped by color, processing each layer separately then merging."""
    # Process layers in user-specified order
    all_layer_svgs = []
    for i, layer_name in enumerate(copper_layers):
        # Skip through holes on all layers except the last one (KiCad optimization)
        is_last_layer = i == len(copper_layers) - 1
        layer_net_svgs = _generate_grouped_net_svgs_single_layer(
            pcb_file,
            layer_name,
            output_dir,
            active_nets,
            net_colors,
            keep_pcb=keep_pcb,
            skip_zones=skip_zones,
            skip_through_holes=not is_last_layer,
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
    skip_through_holes: bool = False,
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
        logger.debug(f"  Default color nets on {layer_name}: {default_nets}")
        layer_suffix = layer_name.replace(".", "_")
        default_svg = output_dir / f"default_nets_{layer_suffix}.svg"

        try:
            # Use optimized approach for default nets
            generate_svg(
                pcb_file,
                layer_name,
                default_svg,
                net_names=set(default_nets),
                skip_zones=skip_zones,
                skip_through_holes=skip_through_holes,
                keep_pcb=keep_pcb,
            )

            # Map all default nets to the same SVG file
            for net_name in default_nets:
                net_svgs[net_name] = default_svg

        except Exception as e:
            logger.warning(f"Failed to generate SVG for default nets: {e}")

    # Generate one SVG per color group and apply color immediately
    for color, nets_with_color in color_groups.items():
        logger.info(
            f"Processing {len(nets_with_color)} nets with color {color} on "
            f"{layer_name}..."
        )
        logger.debug(f"  {color} nets on {layer_name}: {nets_with_color}")
        # Create safe filename from color hex
        safe_color = color.replace("#", "color_").replace("/", "_").replace("\\", "_")
        layer_suffix = layer_name.replace(".", "_")
        raw_svg = output_dir / f"raw_{safe_color}_{layer_suffix}.svg"
        color_svg = output_dir / f"{safe_color}_{layer_suffix}.svg"

        try:
            # Use optimized approach for color group
            generate_svg(
                pcb_file,
                layer_name,
                raw_svg,
                net_names=set(nets_with_color),
                skip_zones=skip_zones,
                skip_through_holes=skip_through_holes,
                keep_pcb=keep_pcb,
            )

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

    return net_svgs


def generate_grouped_non_copper_svgs(
    pcb_file: Path,
    layers: str,
    output_dir: Path,
) -> dict[str, Path]:
    """Generate SVGs for multiple non-copper layers in a single batch operation.

    Args:
        pcb_file: Path to the PCB file
        layers: Comma-separated layer names
        output_dir: Directory where SVGs will be generated

    Returns:
        Dict mapping layer name to generated SVG path
    """
    # All non-copper layers skip drill marks
    generated_svgs = pcbnew_utils.generate_svg_from_board(
        pcb_file, layers, output_dir, skip_through_holes=True
    )

    # Parse layer names to create mapping
    layer_names = [layer.strip() for layer in layers.split(",")]

    if len(generated_svgs) != len(layer_names):
        msg = f"Expected {len(layer_names)} SVGs but got {len(generated_svgs)}"
        raise RuntimeError(msg)

    # Create mapping from layer name to SVG path
    result = {}
    for i, layer_name in enumerate(layer_names):
        if i < len(generated_svgs):
            # Rename to expected format
            expected_name = f"{layer_name.replace('.', '_')}.svg"
            target_path = output_dir / expected_name
            generated_svgs[i].rename(target_path)
            result[layer_name] = target_path

    return result


def get_net_names(pcb_file: Path) -> list[str]:
    """Get all net names from the PCB."""
    net_names = pcbnew_utils.get_net_names(pcb_file)
    return [name for name in net_names if name]  # Filter out empty names
