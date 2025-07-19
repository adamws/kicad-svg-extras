# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Command line interface for net-colored SVG generator."""

import argparse
import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
import fnmatch

from .svg_processor import SVGProcessor


def load_color_config(config_file: Path) -> Dict[str, str]:
    """Load net color configuration from JSON file."""
    with open(config_file, 'r') as f:
        return json.load(f)

def parse_color_value(color_value: str) -> str:
    """Parse various color formats and convert to hex format."""
    import re
    
    color_value = color_value.strip()
    
    # Already hex format: #RRGGBB or #RRGGBBAA
    if re.match(r'^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$', color_value):
        return color_value.upper()[:7]  # Return only RGB part, uppercase
    
    # RGB format: rgb(255, 0, 255) or rgba(255, 0, 255, 1.0)
    rgb_match = re.match(r'^rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)$', color_value)
    if rgb_match:
        r, g, b = [int(val) for val in rgb_match.groups()]
        return f"#{r:02X}{g:02X}{b:02X}"
    
    # HSL format: hsl(300, 100%, 50%)
    hsl_match = re.match(r'^hsl\s*\(\s*(\d+)\s*,\s*(\d+)%\s*,\s*(\d+)%\s*\)$', color_value)
    if hsl_match:
        h, s, l = [int(val) for val in hsl_match.groups()]
        # Simple HSL to RGB conversion
        h = h / 360.0
        s = s / 100.0
        l = l / 100.0
        
        def hsl_to_rgb(h, s, l):
            if s == 0:
                r = g = b = l
            else:
                def hue_to_rgb(p, q, t):
                    if t < 0: t += 1
                    if t > 1: t -= 1
                    if t < 1/6: return p + (q - p) * 6 * t
                    if t < 1/2: return q
                    if t < 2/3: return p + (q - p) * (2/3 - t) * 6
                    return p
                
                q = l * (1 + s) if l < 0.5 else l + s - l * s
                p = 2 * l - q
                r = hue_to_rgb(p, q, h + 1/3)
                g = hue_to_rgb(p, q, h)
                b = hue_to_rgb(p, q, h - 1/3)
            return r, g, b
        
        r, g, b = hsl_to_rgb(h, s, l)
        return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"
    
    # Named colors (basic set)
    named_colors = {
        'red': '#FF0000', 'green': '#008000', 'blue': '#0000FF',
        'yellow': '#FFFF00', 'cyan': '#00FFFF', 'magenta': '#FF00FF',
        'black': '#000000', 'white': '#FFFFFF', 'gray': '#808080',
        'orange': '#FFA500', 'purple': '#800080', 'brown': '#A52A2A'
    }
    
    if color_value.lower() in named_colors:
        return named_colors[color_value.lower()]
    
    # If we can't parse it, return as-is and warn
    logging.warning(f"Could not parse color format: '{color_value}', using as-is")
    return color_value

def load_flexible_colors(config_source: Path) -> Dict[str, str]:
    """Load colors from various file formats with flexible parsing."""
    with open(config_source, 'r') as f:
        data = json.load(f)
    
    # Try to find net_colors in various locations
    net_colors_raw = None
    
    # Option 1: KiCad project format with net_settings.net_colors
    if 'net_settings' in data and 'net_colors' in data['net_settings']:
        net_colors_raw = data['net_settings']['net_colors']
    
    # Option 2: Our custom format with top-level net_colors
    elif 'net_colors' in data:
        net_colors_raw = data['net_colors']
    
    # Option 3: Legacy format - direct net name to color mapping
    else:
        net_colors_raw = data
    
    # Parse all color values to hex format
    converted_colors = {}
    for net_name, color_value in net_colors_raw.items():
        if isinstance(color_value, str) and color_value.strip():
            converted_colors[net_name] = parse_color_value(color_value)
        else:
            logging.warning(f"Skipping invalid color value for net '{net_name}': {color_value}")
    
    return converted_colors

def find_kicad_pro_file(pcb_file: Path) -> Optional[Path]:
    """Find corresponding .kicad_pro file for a .kicad_pcb file."""
    pro_file = pcb_file.with_suffix('.kicad_pro')
    if pro_file.exists():
        return pro_file
    return None

def get_color_for_net(net_name: str, net_colors_config: Dict[str, str]) -> Optional[str]:
    """Get the color for a given net name, supporting wildcards."""
    # Only apply colors if user provided configuration
    if not net_colors_config:
        return None
    
    # Exact match first
    if net_name in net_colors_config:
        return net_colors_config[net_name]

    # Wildcard matches
    # Sort patterns by specificity (longer patterns first)
    sorted_patterns = sorted(net_colors_config.keys(), key=len, reverse=True)
    for pattern in sorted_patterns:
        if '*' in pattern or '?' in pattern or '[' in pattern:  # Check if it's a wildcard pattern
            if fnmatch.fnmatch(net_name, pattern):
                return net_colors_config[pattern]

    # No user-defined color found
    return None




def main():
    parser = argparse.ArgumentParser(
        description="Generate SVG files with custom per-net colors from KiCad PCB files"
    )
    parser.add_argument("pcb_file", type=Path, nargs='?', help="Input KiCad PCB file (.kicad_pcb)")
    parser.add_argument(
        "output_dir", type=Path, nargs='?', help="Output directory for generated SVGs"
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
        "--generate-config",
        action="store_true",
        help="Generate a default color configuration file",
    )
    parser.add_argument(
        "--config-output",
        type=Path,
        default=Path("net_colors.json"),
        help="Output file for generated color configuration",
    )
    parser.add_argument(
        "--front-layers",
        default="B.Cu,F.Cu,F.Silkscreen,Edge.Cuts",
        help="Layer specification for front side",
    )
    parser.add_argument(
        "--back-layers",
        default="F.Cu,B.Cu,B.Silkscreen,Edge.Cuts",
        help="Layer specification for back side",
    )
    parser.add_argument(
        "--list-nets", action="store_true", help="List all nets in the PCB file"
    )
    parser.add_argument(
        "--merge-only",
        action="store_true",
        help="Only merge existing per-net SVGs (skip generation)",
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
        default="#FFFFFF",
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
        help="Include silkscreen layers in the output (F.Silkscreen for front, B.Silkscreen for back)",
    )
    parser.add_argument(
        "--with-edge",
        action="store_true",
        help="Include board edge cuts (Edge.Cuts) in the output",
    )

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    # Validate inputs for SVG generation
    if not args.pcb_file:
        print("Error: PCB file is required for SVG generation")
        sys.exit(1)
        
    if not args.output_dir:
        print("Error: Output directory is required for SVG generation")
        sys.exit(1)
        
    if not args.pcb_file.exists():
        print(f"Error: PCB file not found: {args.pcb_file}")
        sys.exit(1)

    if not args.pcb_file.suffix == '.kicad_pcb':
        print(f"Error: Input file must be a .kicad_pcb file")
        sys.exit(1)

    # Initialize generator
    try:
        from .svg_generator import SVGGenerator

        generator = SVGGenerator(args.pcb_file, args.skip_zones)
        generator.set_layers(args.front_layers, args.back_layers)
    except Exception as e:
        print(f"Error initializing SVG generator: {e}")
        sys.exit(1)

    # List nets if requested
    if args.list_nets:
        net_names = generator.get_net_names()
        print("Available nets:")
        for net_name in sorted(net_names):
            print(f"  {net_name}")
        sys.exit(0)

    # Generate default color configuration if requested
    if args.generate_config:
        net_names = generator.get_net_names()
        # Create empty configuration template for user to fill
        colors = {net_name: "" for net_name in sorted(net_names) if net_name}

        with open(args.config_output, 'w') as f:
            json.dump(colors, f, indent=2)

        print(f"Generated color configuration template: {args.config_output}")
        print(f"Found {len(net_names)} nets")
        print("Please edit the file and add colors for the nets you want to customize.")
        sys.exit(0)

    # Load color configuration with auto-detection
    net_colors_config = {}
    color_source = None
    
    if args.colors:
        # User specified a color file
        if not args.colors.exists():
            print(f"Error: Color configuration file not found: {args.colors}")
            sys.exit(1)
        color_source = args.colors
    else:
        # Try to auto-detect KiCad project file
        kicad_pro_file = find_kicad_pro_file(args.pcb_file)
        if kicad_pro_file:
            color_source = kicad_pro_file
            print(f"Auto-detected KiCad project file: {kicad_pro_file}")
        else:
            print("No color configuration specified and no KiCad project file found")
    
    if color_source:
        try:
            net_colors_config = load_flexible_colors(color_source)
            if net_colors_config:
                print(f"Loaded {len(net_colors_config)} net color(s) from: {color_source}")
            else:
                print(f"No net colors found in: {color_source}")
        except Exception as e:
            print(f"Error loading color configuration from {color_source}: {e}")
            sys.exit(1)

    net_names = generator.get_net_names()

    # Resolve colors for nets with user-provided configuration only
    resolved_net_colors = {}
    for net_name in net_names:
        color = get_color_for_net(net_name, net_colors_config)
        if color:  # Only include nets with user-defined colors
            resolved_net_colors[net_name] = color
            logging.debug(f"Resolved color for net '{net_name}': {color}")
        else:
            logging.debug(f"No custom color defined for net '{net_name}', using KiCad default")

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize processor
    processor = SVGProcessor()

    # Process each side
    sides = ["front", "back"] if args.side == "both" else [args.side]
    
    # Collect SVGs from all sides for potential merging
    all_side_svgs = []
    temp_dirs_to_cleanup = []

    for side in sides:
        print(f"Processing {side} side...")

        if not args.merge_only:
            # Generate color-grouped SVGs for optimization
            temp_dir = args.output_dir / f"temp_{side}"
            net_svgs = generator.generate_color_grouped_svgs(
                side, temp_dir, resolved_net_colors, args.keep_intermediates
            )

            unique_svgs = len(set(net_svgs.values()))
            print(f"Generated {unique_svgs} color-grouped SVGs covering {len(net_svgs)} nets for {side} side")
        else:
            # Look for existing per-net SVGs
            temp_dir = args.output_dir / f"temp_{side}"
            net_svgs = {}
            if temp_dir.exists():
                for svg_file in temp_dir.glob(f"*_{side}.svg"):
                    net_name = svg_file.stem.replace(f"_{side}", "")
                    net_svgs[net_name] = svg_file

            if not net_svgs:
                print(f"No existing per-net SVGs found for {side} side")
                continue

        # Collect unique intermediate SVGs (already colored during generation)
        unique_svgs = list(set(net_svgs.values()))
        
        # Generate additional layers if requested and build proper layering order
        all_svgs_to_merge = []
        
        # Layer 1: Edge cuts (background)
        if args.with_edge:
            edge_svg = temp_dir / f"edge_cuts_{side}.svg"
            try:
                generator.generate_edge_cuts_svg(edge_svg)
                all_svgs_to_merge.append(edge_svg)
                print(f"Generated edge cuts SVG: {edge_svg.name}")
            except Exception as e:
                print(f"Warning: Failed to generate edge cuts SVG: {e}")
        
        # Layer 2: Copper layers (middle)
        all_svgs_to_merge.extend(unique_svgs)
        
        # Layer 3: Silkscreen (top)
        if args.with_silkscreen:
            silkscreen_svg = temp_dir / f"silkscreen_{side}.svg"
            try:
                generator.generate_silkscreen_svg(side, silkscreen_svg)
                all_svgs_to_merge.append(silkscreen_svg)
                print(f"Generated silkscreen SVG: {silkscreen_svg.name}")
            except Exception as e:
                print(f"Warning: Failed to generate silkscreen SVG: {e}")
        
        # Create merged SVG for this side with proper layer ordering
        side_output_file = args.output_dir / f"{side}_colored.svg"

        try:
            processor.merge_svg_files(all_svgs_to_merge, side_output_file)
            if not args.no_background:
                processor._add_background_to_svg(side_output_file, args.background_color)
            print(f"Created colored SVG: {side_output_file}")
            all_side_svgs.append(side_output_file)
                    
        except Exception as e:
            print(f"Error creating colored SVG for {side} side: {e}")
            continue

        # Track temp directories for cleanup
        if not args.merge_only and not args.keep_intermediates:
            temp_dirs_to_cleanup.append(temp_dir)
        elif args.keep_intermediates and temp_dir.exists():
            print(f"Intermediate files kept in: {temp_dir}")

    # If both sides were processed, merge them into a single file
    if args.side == "both" and len(all_side_svgs) == 2:
        merged_output = args.output_dir / "colored.svg"
        print(f"Merging both sides into: {merged_output}")
        
        try:
            processor.merge_svg_files(all_side_svgs, merged_output)
            if not args.no_background:
                processor._add_background_to_svg(merged_output, args.background_color)
            print(f"Created merged SVG: {merged_output}")
            
            # Remove individual side files if merge was successful
            for side_svg in all_side_svgs:
                if side_svg.exists():
                    side_svg.unlink()
                    
        except Exception as e:
            print(f"Error merging sides: {e}")
            print("Individual side files have been kept.")

    # Clean up temporary files
    for temp_dir in temp_dirs_to_cleanup:
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    print("SVG generation completed!")


if __name__ == "__main__":
    main()
