# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""SVG processing utilities for color modification and merging."""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class SVGProcessor:
    """Process SVG files to apply custom colors and merge multiple SVGs."""

    def __init__(self):
        self.svg_ns = "http://www.w3.org/2000/svg"
        ET.register_namespace('', self.svg_ns)

    def _find_copper_color(self, svg_file: Path) -> Optional[str]:
        """Find the copper color used in the SVG."""
        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Look for copper-specific colors (avoid black/white which are usually backgrounds or holes)
        copper_colors = []

        # Look for colors in both groups and paths
        for element in root.findall(f".//{{{self.svg_ns}}}g") + root.findall(f".//{{{self.svg_ns}}}path"):
            style = element.attrib.get('style', '')
            if 'fill:' in style:
                # Extract fill color from style
                fill_start = style.find('fill:') + 5
                fill_end = style.find(';', fill_start)
                if fill_end == -1:
                    fill_end = len(style)
                color = style[fill_start:fill_end].strip()
                if color.startswith('#') and len(color) == 7:
                    # Skip common non-copper colors
                    if color.upper() not in ['#000000', '#FFFFFF']:
                        copper_colors.append(color)

            # Also check fill attribute
            fill = element.attrib.get('fill', '')
            if fill.startswith('#') and len(fill) == 7:
                # Skip common non-copper colors
                if fill.upper() not in ['#000000', '#FFFFFF']:
                    copper_colors.append(fill)

        # Return the first copper color found, or the default KiCad copper color
        if copper_colors:
            return copper_colors[0]

        return None

    def change_svg_color(
        self,
        svg_file: Path,
        old_color: str,
        new_color: str,
        output_file: Optional[Path] = None,
    ) -> Path:
        """Change all instances of old_color to new_color in SVG."""
        if output_file is None:
            output_file = svg_file

        # Read SVG as text for simple color replacement
        with open(svg_file, 'r') as f:
            content = f.read()

        # Replace colors in various formats
        content = content.replace(old_color.upper(), new_color.upper())
        content = content.replace(old_color.lower(), new_color.lower())

        # Also handle RGB format if needed
        if old_color.startswith('#') and len(old_color) == 7:
            # Convert hex to RGB values
            r = int(old_color[1:3], 16)
            g = int(old_color[3:5], 16)
            b = int(old_color[5:7], 16)
            rgb_old = f"rgb({r},{g},{b})"

            if new_color.startswith('#') and len(new_color) == 7:
                r_new = int(new_color[1:3], 16)
                g_new = int(new_color[3:5], 16)
                b_new = int(new_color[5:7], 16)
                rgb_new = f"rgb({r_new},{g_new},{b_new})"
                content = content.replace(rgb_old, rgb_new)

        with open(output_file, 'w') as f:
            f.write(content)

        return output_file

    def apply_net_color(
        self, svg_file: Path, net_color: str, output_file: Optional[Path] = None
    ) -> Path:
        """Apply a specific color to a net SVG."""
        if output_file is None:
            output_file = svg_file

        # Find the current copper color
        current_color = self._find_copper_color(svg_file)

        if current_color:
            logging.debug(f"Recoloring net SVG from {current_color} to {net_color}")
            return self.change_svg_color(
                svg_file, current_color, net_color, output_file
            )
        else:
            logging.debug(f"No specific copper color found, defaulting to #C83434 and recoloring to {net_color}")
            # Default copper color if not found
            return self.change_svg_color(svg_file, '#C83434', net_color, output_file)

    def get_svg_dimensions(self, svg_file: Path) -> Tuple[str, str]:
        """Get SVG width and height."""
        tree = ET.parse(svg_file)
        root = tree.getroot()

        width = root.attrib.get('width', '100%')
        height = root.attrib.get('height', '100%')

        return width, height

    def get_svg_viewbox(self, svg_file: Path) -> Optional[str]:
        """Get SVG viewBox attribute."""
        tree = ET.parse(svg_file)
        root = tree.getroot()

        return root.attrib.get('viewBox')

    def merge_svg_files(
        self, svg_files: List[Path], output_file: Path, base_svg: Optional[Path] = None
    ) -> None:
        """Merge multiple SVG files into one."""
        if not svg_files:
            raise ValueError("No SVG files to merge")

        # Parse all SVG files to determine unified viewBox
        all_files = []
        if base_svg and base_svg.exists():
            all_files.append(base_svg)
        all_files.extend(svg_files)

        # Calculate unified viewBox dimensions
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')

        for svg_file in all_files:
            if not svg_file.exists():
                continue

            tree = ET.parse(svg_file)
            root = tree.getroot()
            viewbox = root.attrib.get('viewBox')

            if viewbox:
                x, y, w, h = map(float, viewbox.split())
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x + w)
                max_y = max(max_y, y + h)

        # Calculate unified dimensions
        unified_width = max_x - min_x
        unified_height = max_y - min_y
        unified_viewbox = f"{min_x} {min_y} {unified_width} {unified_height}"

        # Use simple string-based approach to avoid XML namespace issues
        svg_content = f'''<?xml version="1.0" standalone="no"?>
 <!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
 "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg
  xmlns:svg="http://www.w3.org/2000/svg"
  xmlns="http://www.w3.org/2000/svg"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  version="1.1"
  width="{unified_width}cm" height="{unified_height}cm" viewBox="{unified_viewbox}">
<title>Merged SVG with per-net colors</title>
  <desc>Generated by net_colored_svg tool</desc>
'''

        # Extract content from all SVG files
        for svg_file in svg_files:
            if not svg_file.exists():
                continue

            with open(svg_file, 'r') as f:
                content = f.read()

            # Extract groups and elements between <svg> and </svg>
            start = content.find('<g')
            end = content.rfind('</g>') + 4

            if start != -1 and end != -1:
                group_content = content[start:end]
                # Skip background rectangles
                if 'fill="#282A36"' not in group_content:
                    svg_content += group_content + '\n'

        svg_content += '</svg>'

        # Write merged SVG
        with open(output_file, 'w') as f:
            f.write(svg_content)

    def _add_background_to_svg(self, svg_file: Path, background_color: str) -> None:
        """Add dark background to SVG file."""
        tree = ET.parse(svg_file)
        root = tree.getroot()

        desc = root.find(f".//{{{self.svg_ns}}}desc")
        if desc is not None:
            svg_w = root.attrib.get("width", "")
            svg_h = root.attrib.get("height", "")

            parent = root
            children = list(parent)
            desc_index = children.index(desc)

            # Add dark background
            rect = ET.Element(
                "rect", x="0", y="0", width=svg_w, height=svg_h, fill=background_color
            )
            parent.insert(desc_index + 1, rect)

            tree.write(svg_file, encoding="unicode")

    def create_colored_svg(
        self,
        net_svgs: Dict[str, Path],
        net_colors: Dict[str, str],
        output_file: Path,
        base_svg: Optional[Path] = None,
        add_background: bool = True,
        background_color: str = "#FFFFFF",
    ) -> None:
        """Create a merged SVG with custom colors for each net."""
        colored_svgs = []

        # Apply colors to unique SVG files only
        processed_svgs = set()
        
        for net_name, svg_file in net_svgs.items():
            # Skip if we've already processed this SVG file
            if svg_file in processed_svgs:
                continue
            processed_svgs.add(svg_file)
            
            if net_name in net_colors:
                logging.debug(f"Applying color {net_colors[net_name]} to SVG {svg_file.name}")
                # Create temporary colored SVG
                colored_svg = svg_file.parent / f"colored_{svg_file.name}"
                self.apply_net_color(svg_file, net_colors[net_name], colored_svg)
                colored_svgs.append(colored_svg)
            else:
                logging.debug(f"No custom color defined, preserving KiCad's original color for {svg_file.name}")
                colored_svgs.append(svg_file)

        # Merge all colored SVGs and add background
        self.merge_svg_files(colored_svgs, output_file, base_svg)
        if add_background:
            self._add_background_to_svg(output_file, background_color)

        # Clean up temporary colored SVGs
        for svg_file in colored_svgs:
            if svg_file.name.startswith("colored_") and svg_file.exists():
                svg_file.unlink()
