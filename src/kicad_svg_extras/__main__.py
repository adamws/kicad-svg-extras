# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Command line interface for net-colored SVG generator."""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional

from kicad_svg_extras import svg_generator
from kicad_svg_extras.colors import (
    DEFAULT_BACKGROUND_LIGHT,
    load_color_config,
    parse_color,
    resolve_net_color,
)
from kicad_svg_extras.layers import (
    get_copper_layers,
    get_non_copper_layers,
    parse_layer_list,
    sort_layers_by_stackup,
    validate_layers,
)
from kicad_svg_extras.logging import setup_logging
from kicad_svg_extras.svg_processor import (
    add_background_to_svg,
    fit_svg_to_content,
    merge_svg_files,
)

logger = logging.getLogger(__name__)


def find_kicad_pro_file(pcb_file: Path) -> Optional[Path]:
    """Find corresponding .kicad_pro file for a .kicad_pcb file."""
    pro_file = pcb_file.with_suffix(".kicad_pro")
    if pro_file.exists():
        return pro_file
    return None


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate SVG files with custom per-net colors from KiCad PCB files"
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s --net-color 'GND:green' --net-color 'VCC:red' "
            "board.kicad_pcb output/\n"
            "  %(prog)s --net-color 'SIGNAL*:blue' --side front "
            "board.kicad_pcb output/\n"
            "  %(prog)s --colors colors.json board.kicad_pcb output/"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pcb_file", type=Path, nargs="?", help="Input KiCad PCB file (.kicad_pcb)"
    )
    parser.add_argument(
        "output_dir", type=Path, nargs="?", help="Output directory for generated SVGs"
    )
    parser.add_argument(
        "--layers",
        type=str,
        default="F.Cu,B.Cu",
        help=(
            "Comma-separated list of KiCad layer names to process "
            "(e.g., 'F.Cu,B.Cu,In1.Cu,In2.Cu' or 'F.Cu,F.SilkS,Edge.Cuts'). "
            "Default: F.Cu,B.Cu"
        ),
    )
    parser.add_argument(
        "--colors",
        type=Path,
        metavar="CONFIG_FILE",
        help="JSON file with net name to color mapping",
    )
    parser.add_argument(
        "--net-color",
        action="append",
        metavar="NET_NAME:COLOR",
        help=(
            "Set color for specific net (format: 'net_name:color').  "
            "Can be used multiple times. Supports hex (#FF0000), "
            "RGB (rgb(255,0,0)), or named colors (red)."
        ),
    )
    parser.add_argument(
        "--use-css-classes",
        action="store_true",
        help=(
            "Use CSS classes for styling instead of hardcoded colors. "
            "Generates individual SVG per net (slower) but allows easy "
            "color customization via CSS. Classes: .net-<name> { fill: color; }"
        ),
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Keep intermediate files for debugging",
    )
    parser.add_argument(
        "--no-background",
        action="store_true",
        help="Do not add a background to the output SVGs",
    )
    parser.add_argument(
        "--background-color",
        type=str,
        default=DEFAULT_BACKGROUND_LIGHT,
        help="Background color for the output SVGs (default: #FFFFFF)",
    )
    parser.add_argument(
        "--skip-zones",
        action="store_true",
        help="Skip drawing zones in the output SVGs",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--fit-to-content",
        action="store_true",
        help=(
            "Remove unnecessary margins from final SVG by fitting to content. "
            "Requires Inkscape to be available in PATH."
        ),
    )
    parser.add_argument(
        "--reverse-stackup",
        action="store_true",
        help=(
            "Reverse the layer stacking order for bottom-to-front view. "
            "Default is front-to-back (top-down view)."
        ),
    )

    args = parser.parse_args()

    # Configure clean logging for CLI application
    setup_logging(level=getattr(logging, args.log_level.upper()))

    # Validate inputs for SVG generation
    if not args.pcb_file:
        logger.error("PCB file is required for SVG generation")
        sys.exit(1)

    if not args.output_dir:
        logger.error("Output directory is required for SVG generation")
        sys.exit(1)

    if not args.pcb_file.exists():
        logger.error(f"PCB file not found: {args.pcb_file}")
        sys.exit(1)

    if not args.pcb_file.suffix == ".kicad_pcb":
        logger.error("Input file must be a .kicad_pcb file")
        sys.exit(1)

    # Load color configuration with auto-detection
    net_colors_config = {}
    color_source = None

    if args.colors:
        # User specified a color file
        if not args.colors.exists():
            logger.error(f"Color configuration file not found: {args.colors}")
            sys.exit(1)
        color_source = args.colors
    else:
        # Try to auto-detect KiCad project file
        kicad_pro_file = find_kicad_pro_file(args.pcb_file)
        if kicad_pro_file:
            color_source = kicad_pro_file
            logger.info(f"Auto-detected KiCad project file: {kicad_pro_file}")
        else:
            logger.info(
                "No color configuration specified and no KiCad project file found"
            )

    if color_source:
        try:
            net_colors_config = load_color_config(color_source)
            if net_colors_config:
                logger.info(
                    f"Loaded {len(net_colors_config)} net color(s) from: {color_source}"
                )
            else:
                logger.info(f"No net colors found in: {color_source}")
        except Exception as e:
            logger.error(f"Error loading color configuration from {color_source}: {e}")
            sys.exit(1)

    # Parse and add CLI net color arguments
    if args.net_color:
        for net_color_arg in args.net_color:
            if ":" not in net_color_arg:
                logger.error(
                    f"Invalid net-color format: '{net_color_arg}'. "
                    "Expected format: 'net_name:color'"
                )
                sys.exit(1)

            net_name, color_value = net_color_arg.split(":", 1)
            net_name = net_name.strip()
            color_value = color_value.strip()

            if not net_name:
                logger.error(f"Empty net name in: '{net_color_arg}'")
                sys.exit(1)

            if not color_value:
                logger.error(f"Empty color value in: '{net_color_arg}'")
                sys.exit(1)

            try:
                parsed_color = parse_color(color_value)
                net_colors_config[net_name] = parsed_color
                logger.info(f"Set color for net '{net_name}': {parsed_color}")
            except Exception as e:
                logger.error(f"Invalid color '{color_value}' for net '{net_name}': {e}")
                sys.exit(1)

    net_names = svg_generator.get_net_names(args.pcb_file)

    # Resolve colors for nets with user-provided configuration only
    resolved_net_colors = {}
    for net_name in net_names:
        color = resolve_net_color(net_name, net_colors_config)
        if color:  # Only include nets with user-defined colors
            resolved_net_colors[net_name] = color
            logger.debug(f"Resolved color for net '{net_name}': {color}")
        else:
            logger.debug(
                f"No custom color defined for net '{net_name}', using KiCad default"
            )

    # Parse and validate layers
    layer_list = parse_layer_list(args.layers)
    if not layer_list:
        logger.error("No layers specified")
        sys.exit(1)

    invalid_layers = validate_layers(layer_list)
    if invalid_layers:
        logger.error(f"Invalid layer names: {', '.join(invalid_layers)}")
        sys.exit(1)

    # Separate copper and non-copper layers
    copper_layers = get_copper_layers(layer_list)
    non_copper_layers = get_non_copper_layers(layer_list)

    if not copper_layers:
        logger.error("At least one copper layer must be specified")
        sys.exit(1)

    logger.info(f"Processing copper layers: {', '.join(copper_layers)}")
    if non_copper_layers:
        logger.info(f"Processing non-copper layers: {', '.join(non_copper_layers)}")

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Process the specified layers
    temp_dir = args.output_dir / "temp"
    temp_dirs_to_cleanup = []

    logger.info(f"Processing layers: {', '.join(layer_list)}")

    # Generate colored SVGs for copper layers (nets)
    net_svgs = svg_generator.generate_color_grouped_svgs(
        args.pcb_file,
        copper_layers,
        temp_dir,
        resolved_net_colors,
        keep_pcb=args.keep_intermediates,
        skip_zones=args.skip_zones,
        use_css_classes=args.use_css_classes,
        reverse_stackup=args.reverse_stackup,
    )

    unique_svgs = len(set(net_svgs.values()))
    logger.info(
        f"Generated {unique_svgs} color-grouped SVGs covering {len(net_svgs)} nets"
    )

    # Collect unique intermediate SVGs (already colored during generation)
    copper_svgs = list(set(net_svgs.values()))

    # Generate SVGs for non-copper layers and build proper layering order
    all_svgs_to_merge = []

    # Sort all layers by stackup order for proper rendering
    sorted_layers = sort_layers_by_stackup(layer_list, reverse=args.reverse_stackup)

    # Add all copper SVGs first (they're already generated and colored)
    all_svgs_to_merge.extend(copper_svgs)

    # Generate SVGs for non-copper layers and insert them in proper order
    non_copper_svgs = {}
    for layer_name in non_copper_layers:
        layer_svg = temp_dir / f"{layer_name.replace('.', '_')}.svg"
        try:
            svg_generator.generate_layer_svg(args.pcb_file, layer_name, layer_svg)
            non_copper_svgs[layer_name] = layer_svg
            logger.info(f"Generated {layer_name} SVG: {layer_svg.name}")
        except Exception as e:
            logger.warning(f"Failed to generate {layer_name} SVG: {e}")

    # Now rebuild the list in proper stackup order
    all_svgs_to_merge = []
    for layer_name in sorted_layers:
        if layer_name in copper_layers:
            # Add copper SVGs in the position of the first copper layer
            if copper_svgs:
                all_svgs_to_merge.extend(copper_svgs)
                copper_svgs = []  # Only add them once
        elif layer_name in non_copper_svgs:
            # Add non-copper layer SVG
            all_svgs_to_merge.append(non_copper_svgs[layer_name])

    # Create merged SVG with proper layer ordering
    layer_suffix = "_".join(copper_layers).replace(".", "_")
    output_file = args.output_dir / f"colored_{layer_suffix}.svg"

    try:
        merge_svg_files(all_svgs_to_merge, output_file)

        # Fit to content if requested (before adding background)
        if args.fit_to_content:
            try:
                fit_svg_to_content(output_file)
            except RuntimeError as e:
                logger.warning(f"Failed to fit SVG to content: {e}")

        if not args.no_background:
            add_background_to_svg(output_file, args.background_color)
        logger.info(f"Created colored SVG: {output_file}")

    except Exception as e:
        logger.error(f"Error creating colored SVG: {e}")
        sys.exit(1)

    # Track temp directories for cleanup
    if not args.keep_intermediates:
        temp_dirs_to_cleanup.append(temp_dir)
    elif args.keep_intermediates and temp_dir.exists():
        logger.info(f"Intermediate files kept in: {temp_dir}")

    # Clean up temporary files
    for temp_dir in temp_dirs_to_cleanup:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    logger.info("SVG generation completed!")


if __name__ == "__main__":
    main()
