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
    validate_layers,
)
from kicad_svg_extras.logging import setup_logging
from kicad_svg_extras.pcbnew_utils import (
    filter_layers_by_pcb_availability,
    get_pcb_forced_svg_params,
)
from kicad_svg_extras.svg_processor import (
    add_background_to_svg,
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
        "--no-fit-to-content",
        action="store_true",
        help=(
            "Disable automatic fitting of SVG to content bounds "
            "(keeps original large canvas)"
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

    net_names = svg_generator.get_net_names(Path(args.pcb_file))

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

    # Filter layers based on what's actually enabled in the PCB
    layer_list = filter_layers_by_pcb_availability(layer_list, str(args.pcb_file))
    if not layer_list:
        logger.error("No enabled layers found in PCB file")
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
        use_aux_origin=not args.no_fit_to_content,
    )

    unique_svgs = len(set(net_svgs.values()))
    logger.info(
        f"Generated {unique_svgs} color-grouped SVGs covering {len(net_svgs)} nets"
    )

    # Collect unique intermediate SVGs preserving user-specified layer order
    seen = set()
    copper_svgs = []
    # Process layers in user-specified order to maintain proper stacking
    for layer in copper_layers:
        for svg_path in net_svgs.values():
            if svg_path not in seen and layer.replace(".", "_") in svg_path.name:
                seen.add(svg_path)
                copper_svgs.append(svg_path)

    # Generate SVGs for non-copper layers and build proper layering order
    all_svgs_to_merge = []

    # Add all copper SVGs first (they're already generated and colored)
    all_svgs_to_merge.extend(copper_svgs)

    # Generate SVGs for non-copper layers and insert them in proper order
    non_copper_svgs = {}

    # Process all non-copper layers together using comma-separated layer capability
    if non_copper_layers:
        layers_str = ",".join(non_copper_layers)
        generated_svgs = svg_generator.generate_grouped_non_copper_svgs(
            args.pcb_file,
            layers_str,
            temp_dir,
            use_aux_origin=not args.no_fit_to_content,
        )
        non_copper_svgs.update(generated_svgs)
        logger.info(f"Generated {len(generated_svgs)} non-copper SVGs in one batch")

    # Now rebuild the list in proper stackup order
    logger.debug(f"Building final SVG merge order from {len(layer_list)} layers")
    logger.debug(f"Copper layers to merge: {copper_layers}")
    logger.debug(f"Non-copper layers available: {list(non_copper_svgs.keys())}")

    all_svgs_to_merge = []
    copper_added = False

    for layer_name in layer_list:
        if layer_name in copper_layers:
            # Add copper SVGs in the position of the first copper layer
            if copper_svgs and not copper_added:
                logger.debug(
                    f"Adding {len(copper_svgs)} copper layer SVGs at position of "
                    f"{layer_name}"
                )
                for j, copper_svg in enumerate(copper_svgs):
                    logger.debug(f"  Copper {j+1}: {copper_svg.name}")
                all_svgs_to_merge.extend(copper_svgs)
                copper_added = True
        elif layer_name in non_copper_svgs:
            # Add non-copper layer SVG
            logger.debug(
                f"Adding non-copper layer: {layer_name} -> "
                f"{non_copper_svgs[layer_name].name}"
            )
            all_svgs_to_merge.append(non_copper_svgs[layer_name])

    # Create merged SVG with proper layer ordering
    layer_suffix = "_".join(layer_list).replace(".", "_")
    output_file = args.output_dir / f"colored_{layer_suffix}.svg"

    try:
        # Check if we need to force dimensions due to KiCad size limits
        forced_width = forced_height = forced_viewbox = None
        if not args.no_fit_to_content:
            needs_forcing, forced_width, forced_height, forced_viewbox = (
                get_pcb_forced_svg_params(args.pcb_file)
            )
            if needs_forcing:
                logger.debug(
                    f"Forcing SVG dimensions to {forced_width}x{forced_height} "
                    f"viewBox={forced_viewbox} due to KiCad page size limits"
                )

        merge_svg_files(
            all_svgs_to_merge,
            output_file,
            forced_width=forced_width,
            forced_height=forced_height,
            forced_viewbox=forced_viewbox,
        )
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
