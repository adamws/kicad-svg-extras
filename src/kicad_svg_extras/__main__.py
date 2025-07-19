# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
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
    resolve_net_color,
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
        )
    )
    parser.add_argument(
        "pcb_file", type=Path, nargs="?", help="Input KiCad PCB file (.kicad_pcb)"
    )
    parser.add_argument(
        "output_dir", type=Path, nargs="?", help="Output directory for generated SVGs"
    )
    parser.add_argument(
        "--side",
        choices=["front", "back", "both"],
        default="both",
        help="Which side to generate (default: both)",
    )
    parser.add_argument(
        "--colors",
        type=Path,
        metavar="CONFIG_FILE",
        help="JSON file with net name to color mapping",
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
        "--with-silkscreen",
        action="store_true",
        help=(
            "Include silkscreen layers in the output "
            "(F.Silkscreen for front, B.Silkscreen for back)"
        ),
    )
    parser.add_argument(
        "--with-edge",
        action="store_true",
        help="Include board edge cuts (Edge.Cuts) in the output",
    )
    parser.add_argument(
        "--nightly",
        action="store_true",
        help=("Use kicad-cli-nightly instead of kicad-cli (for KiCad nightly builds)"),
    )

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    # Validate inputs for SVG generation
    if not args.pcb_file:
        logger.info("Error: PCB file is required for SVG generation")
        sys.exit(1)

    if not args.output_dir:
        logger.info("Error: Output directory is required for SVG generation")
        sys.exit(1)

    if not args.pcb_file.exists():
        logger.info(f"Error: PCB file not found: {args.pcb_file}")
        sys.exit(1)

    if not args.pcb_file.suffix == ".kicad_pcb":
        logger.info("Error: Input file must be a .kicad_pcb file")
        sys.exit(1)

    # Initialize kicad CLI command
    kicad_cli_cmd = "kicad-cli-nightly" if args.nightly else "kicad-cli"

    # Load color configuration with auto-detection
    net_colors_config = {}
    color_source = None

    if args.colors:
        # User specified a color file
        if not args.colors.exists():
            logger.info(f"Error: Color configuration file not found: {args.colors}")
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

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Process each side
    sides = ["front", "back"] if args.side == "both" else [args.side]

    # Collect SVGs from all sides for potential merging
    all_side_svgs = []
    temp_dirs_to_cleanup = []

    for side in sides:
        logger.info(f"Processing {side} side...")

        temp_dir = args.output_dir / f"temp_{side}"
        net_svgs = svg_generator.generate_color_grouped_svgs(
            args.pcb_file,
            side,
            temp_dir,
            resolved_net_colors,
            keep_pcb=args.keep_intermediates,
            kicad_cli_cmd=kicad_cli_cmd,
            skip_zones=args.skip_zones,
        )

        unique_svgs = len(set(net_svgs.values()))
        logger.info(
            f"Generated {unique_svgs} color-grouped SVGs covering {len(net_svgs)} "
            f"nets for {side} side"
        )

        # Collect unique intermediate SVGs (already colored during generation)
        unique_svgs = list(set(net_svgs.values()))

        # Generate additional layers if requested and build proper layering order
        all_svgs_to_merge = []

        # Layer 1: Edge cuts (background)
        if args.with_edge:
            edge_svg = temp_dir / f"edge_cuts_{side}.svg"
            try:
                svg_generator.generate_edge_cuts_svg(
                    args.pcb_file, edge_svg, kicad_cli_cmd
                )
                all_svgs_to_merge.append(edge_svg)
                logger.info(f"Generated edge cuts SVG: {edge_svg.name}")
            except Exception as e:
                logger.warning(f"Warning: Failed to generate edge cuts SVG: {e}")

        # Layer 2: Copper layers (middle)
        all_svgs_to_merge.extend(unique_svgs)

        # Layer 3: Silkscreen (top)
        if args.with_silkscreen:
            silkscreen_svg = temp_dir / f"silkscreen_{side}.svg"
            try:
                svg_generator.generate_silkscreen_svg(
                    args.pcb_file, side, silkscreen_svg, kicad_cli_cmd
                )
                all_svgs_to_merge.append(silkscreen_svg)
                logger.info(f"Generated silkscreen SVG: {silkscreen_svg.name}")
            except Exception as e:
                logger.warning(f"Warning: Failed to generate silkscreen SVG: {e}")

        # Create merged SVG for this side with proper layer ordering
        side_output_file = args.output_dir / f"{side}_colored.svg"

        try:
            merge_svg_files(all_svgs_to_merge, side_output_file)
            if not args.no_background:
                add_background_to_svg(
                    side_output_file, args.background_color
                )
            logger.info(f"Created colored SVG: {side_output_file}")
            all_side_svgs.append(side_output_file)

        except Exception as e:
            logger.info(f"Error creating colored SVG for {side} side: {e}")
            continue

        # Track temp directories for cleanup
        if not args.keep_intermediates:
            temp_dirs_to_cleanup.append(temp_dir)
        elif args.keep_intermediates and temp_dir.exists():
            logger.info(f"Intermediate files kept in: {temp_dir}")

    # If both sides were processed, merge them into a single file
    if args.side == "both" and len(all_side_svgs) == 2:  # noqa: PLR2004
        merged_output = args.output_dir / "colored.svg"
        logger.info(f"Merging both sides into: {merged_output}")

        try:
            merge_svg_files(all_side_svgs, merged_output)
            if not args.no_background:
                add_background_to_svg(merged_output, args.background_color)
            logger.info(f"Created merged SVG: {merged_output}")

            # Remove individual side files if merge was successful
            for side_svg in all_side_svgs:
                if side_svg.exists():
                    side_svg.unlink()

        except Exception as e:
            logger.info(f"Error merging sides: {e}")
            logger.info("Individual side files have been kept.")

    # Clean up temporary files
    for temp_dir in temp_dirs_to_cleanup:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    logger.info("SVG generation completed!")


if __name__ == "__main__":
    main()
