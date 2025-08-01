# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Command line interface for net-colored SVG generator."""

import argparse
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from kicad_svg_extras import svg_generator
from kicad_svg_extras.colors import (
    DEFAULT_BACKGROUND_LIGHT,
    load_color_config,
    net_layer_to_css_class,
    net_name_to_css_class,
    parse_color,
    resolve_net_color,
)
from kicad_svg_extras.layers import (
    get_copper_layers,
    get_non_copper_layers,
    parse_layer_list,
    validate_layers,
)
from kicad_svg_extras.log_setup import setup_logging
from kicad_svg_extras.pcbnew_utils import (
    filter_layers_by_pcb_availability,
    get_pcb_forced_svg_params,
)
from kicad_svg_extras.svg_processor import (
    add_background_to_svg,
    merge_svg_files,
    remove_empty_groups,
)

logger = logging.getLogger(__name__)


def find_kicad_pro_file(pcb_file: Path) -> Optional[Path]:
    """Find corresponding .kicad_pro file for a .kicad_pcb file."""
    pro_file = pcb_file.with_suffix(".kicad_pro")
    if pro_file.exists():
        return pro_file
    return None


def _export_metadata(
    metadata_file: Path,
    net_names: set[str],
    resolved_net_colors: dict[str, str],
    layer_list: list[str],
    *,
    use_css_classes: bool,
) -> None:
    """Export net name to CSS class mapping metadata to JSON file.

    Args:
        metadata_file: Path to output metadata JSON file
        net_names: Set of all net names from PCB
        resolved_net_colors: Dictionary of net names to their colors
        layer_list: List of layers being processed
        use_css_classes: Whether CSS classes are being used
    """
    if not use_css_classes:
        logger.warning("Metadata export is only meaningful with --use-css-classes")

    # Ensure parent directory exists
    metadata_file.parent.mkdir(parents=True, exist_ok=True)

    # Get copper layers for CSS class generation
    copper_layers = get_copper_layers(layer_list)

    metadata: dict[str, Any] = {
        "format_version": "1.0",
        "generated_with_css_classes": use_css_classes,
        "layers": layer_list,
        "copper_layers": copper_layers,
        "nets": {},
    }

    for net_name in sorted(net_names):
        css_classes: dict[str, str] = {}
        net_info: dict[str, Any] = {
            "original_name": net_name,
            "color": resolved_net_colors.get(
                net_name, "#C83434"
            ),  # Default copper color
            "css_classes": css_classes,
        }

        if use_css_classes:
            # Generate CSS classes for each copper layer
            for layer in copper_layers:
                css_class = net_layer_to_css_class(net_name, layer)
                css_classes[layer] = css_class

            # Also include generic CSS class (no layer suffix)
            net_info["css_class_generic"] = net_name_to_css_class(net_name)

        metadata["nets"][net_name] = net_info

    # Write metadata to file
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.debug(
        f"Exported metadata for {len(net_names)} nets with {len(copper_layers)} "
        "copper layers"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate SVG files with custom per-net colors from KiCad PCB files"
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s --output board.svg --net-color 'GND:green' "
            "--net-color 'VCC:red' board.kicad_pcb\n"
            "  %(prog)s --output board.svg --net-color 'SIGNAL*:blue' "
            "board.kicad_pcb\n"
            "  %(prog)s --output board.svg --colors colors.json board.kicad_pcb"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pcb_file", type=Path, help="Input KiCad PCB file (.kicad_pcb)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        metavar="OUTPUT_FILE",
        help="Output SVG file path",
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
        choices=["none", "all", "edges_only"],
        default="edges_only",
        help=(
            "Control how bounding box is calculated for fit-to-content: "
            "'none' disables fitting (keeps original canvas), "
            "'all' uses all PCB components, "
            "'edges_only' uses only board edges (default)"
        ),
    )
    parser.add_argument(
        "--export-metadata",
        type=Path,
        metavar="METADATA_FILE",
        help=(
            "Export net name to CSS class mapping metadata to JSON file. "
            "Only useful with --use-css-classes. Contains mapping of actual "
            "net names to their CSS class names for integration purposes."
        ),
    )
    parser.add_argument(
        "--ignore-project-colors",
        action="store_true",
        help="Ignore net colors defined in the KiCad project file.",
    )
    parser.add_argument(
        "-t",
        "--theme",
        type=str,
        default="user",
        metavar="THEME_NAME",
        help=(
            "Color theme to use (will default to PCB editor settings if "
            "theme not found)"
        ),
    )

    args = parser.parse_args()

    # Configure clean logging for CLI application
    setup_logging(level=getattr(logging, args.log_level.upper()))

    # Validate inputs for SVG generation

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
    elif not args.ignore_project_colors:
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

    # Create temporary workspace directory
    temp_workspace = Path(tempfile.mkdtemp(prefix="kicad_svg_"))
    temp_dir = temp_workspace / "temp"
    temp_dirs_to_cleanup = []

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Processing layers: {', '.join(layer_list)}")

    # Generate colored SVGs for copper layers (nets)
    edges_only = args.fit_to_content == "edges_only"
    net_svgs = svg_generator.generate_color_grouped_svgs(
        args.pcb_file,
        copper_layers,
        temp_dir,
        resolved_net_colors,
        keep_pcb=args.keep_intermediates,
        skip_zones=args.skip_zones,
        use_css_classes=args.use_css_classes,
        use_aux_origin=args.fit_to_content != "none",
        bound_with_edges_only=edges_only,
        theme=args.theme,
    )

    unique_svgs = len(set(net_svgs.values()))
    logger.info(
        f"Generated {unique_svgs} color-grouped SVGs covering {len(net_svgs)} nets"
    )

    # Collect unique intermediate SVGs preserving user-specified layer order
    logger.debug(f"Available net_svgs.values(): {[str(p) for p in net_svgs.values()]}")

    # Determine if we're in CSS mode by checking if any styled SVGs exist
    css_mode = len(list(temp_dir.glob("*_styled.svg"))) > 0
    logger.debug(f"Detected CSS mode: {css_mode}")

    copper_svgs = []
    if css_mode:
        # CSS mode: collect all *_styled.svg files for each copper layer
        for layer in copper_layers:
            layer_name = layer.replace(".", "_")
            logger.debug(
                f"Looking for styled SVGs for layer: {layer} "
                f"(pattern: *{layer_name}_styled.svg)"
            )

            # Find all styled SVGs for this layer
            layer_styled_svgs = list(temp_dir.glob(f"*{layer_name}_styled.svg"))
            logger.debug(
                f"Found {len(layer_styled_svgs)} styled SVGs for {layer}: "
                f"{[p.name for p in layer_styled_svgs]}"
            )

            copper_svgs.extend(layer_styled_svgs)
    else:
        # Non-CSS mode: use the original logic with net_svgs.values()
        seen = set()
        # Process layers in user-specified order to maintain proper stacking
        for layer in copper_layers:
            for svg_path in net_svgs.values():
                if svg_path not in seen and layer.replace(".", "_") in svg_path.name:
                    seen.add(svg_path)
                    copper_svgs.append(svg_path)

    logger.debug(f"Total copper SVGs to merge: {len(copper_svgs)}")
    for i, svg in enumerate(copper_svgs):
        logger.debug(f"  Copper SVG {i+1}: {svg.name}")

    # Generate SVGs for non-copper layers and build proper layering order

    # Generate SVGs for non-copper layers and insert them in proper order
    non_copper_svgs = {}

    # Process all non-copper layers together using comma-separated layer capability
    if non_copper_layers:
        layers_str = ",".join(non_copper_layers)
        generated_svgs = svg_generator.generate_grouped_non_copper_svgs(
            args.pcb_file,
            layers_str,
            temp_dir,
            use_aux_origin=args.fit_to_content != "none",
            bound_with_edges_only=edges_only,
            theme=args.theme,
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

    # Create merged SVG with proper layer ordering in temp workspace
    layer_suffix = "_".join(layer_list).replace(".", "_")
    temp_output_file = temp_workspace / f"colored_{layer_suffix}.svg"

    try:
        # Check if we need to force dimensions due to KiCad size limits
        forced_width = forced_height = forced_viewbox = None
        if args.fit_to_content != "none":
            edges_only = args.fit_to_content == "edges_only"
            needs_forcing, forced_width, forced_height, forced_viewbox = (
                get_pcb_forced_svg_params(args.pcb_file, edges_only=edges_only)
            )
            if needs_forcing:
                logger.debug(
                    f"Forcing SVG dimensions to {forced_width}x{forced_height} "
                    f"viewBox={forced_viewbox} due to KiCad page size limits"
                )

        merge_svg_files(
            all_svgs_to_merge,
            temp_output_file,
            forced_width=forced_width,
            forced_height=forced_height,
            forced_viewbox=forced_viewbox,
        )
        if not args.no_background:
            add_background_to_svg(temp_output_file, args.background_color)

        logger.debug("Running result sanitization")
        logger.debug("  Remove empty groups")
        remove_empty_groups(temp_output_file)

        # Copy final SVG to user-specified output location
        shutil.copy2(temp_output_file, args.output)
        logger.info(f"Created colored SVG: {args.output}")

        # Export metadata if requested
        if args.export_metadata:
            try:
                _export_metadata(
                    args.export_metadata,
                    set(net_names),
                    resolved_net_colors,
                    layer_list,
                    use_css_classes=args.use_css_classes,
                )
                logger.info(f"Exported metadata to: {args.export_metadata}")
            except Exception as e:
                logger.error(f"Error exporting metadata: {e}")
                sys.exit(1)

    except Exception as e:
        logger.error(f"Error creating colored SVG: {e}")
        sys.exit(1)

    # Track temp directories for cleanup
    if not args.keep_intermediates:
        temp_dirs_to_cleanup.extend([temp_dir, temp_workspace])
    elif args.keep_intermediates and temp_workspace.exists():
        logger.info(f"Intermediate files kept in: {temp_workspace}")

    # Clean up temporary files
    for temp_dir_path in temp_dirs_to_cleanup:
        if temp_dir_path.exists():
            shutil.rmtree(temp_dir_path)

    logger.info("SVG generation completed!")


if __name__ == "__main__":
    main()
