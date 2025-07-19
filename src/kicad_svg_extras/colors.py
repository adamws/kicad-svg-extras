# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Color management for KiCad SVG generation."""

import fnmatch
import json
import logging
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default colors used throughout the application
DEFAULT_BACKGROUND_DARK = "#282A36"
DEFAULT_BACKGROUND_LIGHT = "#FFFFFF"

# Color validation constants
MAX_RGB_VALUE = 255

# Non-copper colors to exclude during auto-detection
NON_COPPER_COLORS = frozenset(
    [
        "#000000",  # Black
        "#FFFFFF",  # White
    ]
)

# Named color palette (Web/CSS colors)
NAMED_COLORS = {
    # Basic colors
    "red": "#FF0000",
    "green": "#008000",
    "blue": "#0000FF",
    "yellow": "#FFFF00",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "black": "#000000",
    "white": "#FFFFFF",
    "gray": "#808080",
    "grey": "#808080",  # Alternative spelling
    "orange": "#FFA500",
    "purple": "#800080",
    "brown": "#A52A2A",
    # Extended palette
    "lime": "#00FF00",
    "navy": "#000080",
    "maroon": "#800000",
    "olive": "#808000",
    "aqua": "#00FFFF",
    "fuchsia": "#FF00FF",
    "silver": "#C0C0C0",
    "teal": "#008080",
    "pink": "#FFC0CB",
    "gold": "#FFD700",
    "indigo": "#4B0082",
    "violet": "#EE82EE",
    "turquoise": "#40E0D0",
    "coral": "#FF7F50",
    "salmon": "#FA8072",
    "khaki": "#F0E68C",
    "plum": "#DDA0DD",
    "orchid": "#DA70D6",
    "tan": "#D2B48C",
    "beige": "#F5F5DC",
    "mint": "#98FB98",
    "lavender": "#E6E6FA",
    "peach": "#FFCBA4",
}


class ColorError(Exception):
    """Exception raised for color-related errors."""


def parse_color(color_value: str) -> str:
    """Parse various color formats and convert to hex format.

    Args:
        color_value: Color in hex, RGB, or named format

    Returns:
        Color in #RRGGBB hex format

    Raises:
        ColorError: If color format is invalid
    """
    if not isinstance(color_value, str):
        msg = f"Color value must be a string, got {type(color_value)}"
        raise ColorError(msg)

    color_value = color_value.strip()
    if not color_value:
        msg = "Color value cannot be empty"
        raise ColorError(msg)

    # Already hex format: #RRGGBB or #RRGGBBAA
    if re.match(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$", color_value):
        return color_value.upper()[:7]  # Return only RGB part, uppercase

    # RGB format: rgb(255, 0, 255) or rgba(255, 0, 255, 1.0)
    rgb_match = re.match(
        r"^rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)$",
        color_value,
    )
    if rgb_match:
        r, g, b = [int(val) for val in rgb_match.groups()]
        # Validate RGB values
        if not all(0 <= val <= MAX_RGB_VALUE for val in (r, g, b)):
            msg = f"RGB values must be between 0-{MAX_RGB_VALUE}, got ({r}, {g}, {b})"
            raise ColorError(msg)
        return f"#{r:02X}{g:02X}{b:02X}"

    # Named colors
    if color_value.lower() in NAMED_COLORS:
        return NAMED_COLORS[color_value.lower()]

    # If we can't parse it, raise an error
    msg = f"Invalid color format: '{color_value}'"
    raise ColorError(msg)


def validate_hex_color(hex_color: str) -> bool:
    """Validate if a string is a valid hex color.

    Args:
        hex_color: String to validate

    Returns:
        True if valid hex color, False otherwise
    """
    return bool(re.match(r"^#[0-9A-Fa-f]{6}$", hex_color))


def load_color_config(config_file: Path) -> dict[str, str]:
    """Load net color configuration from JSON file.

    Args:
        config_file: Path to JSON configuration file

    Returns:
        Dictionary mapping net names to hex colors

    Raises:
        ColorError: If file cannot be loaded or parsed
    """
    try:
        with open(config_file) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        msg = f"Failed to load color configuration from {config_file}: {e}"
        raise ColorError(msg) from e

    # Try to find net_colors in various locations
    net_colors_raw = None

    # Option 1: KiCad project format with net_settings.net_colors
    if "net_settings" in data and "net_colors" in data["net_settings"]:
        net_colors_raw = data["net_settings"]["net_colors"]
    # Option 2: Our custom format with top-level net_colors
    elif "net_colors" in data:
        net_colors_raw = data["net_colors"]
    # Option 3: Legacy format - direct net name to color mapping
    else:
        net_colors_raw = data

    # Handle case where no net colors found or net_colors_raw is None
    if net_colors_raw is None or not isinstance(net_colors_raw, dict):
        logger.info(f"No net color configuration found in {config_file}")
        return {}

    # Parse all color values to hex format
    converted_colors = {}
    for net_name, color_value in net_colors_raw.items():
        if not isinstance(color_value, str) or not color_value.strip():
            logger.warning(
                f"Skipping invalid color value for net '{net_name}': {color_value}"
            )
            continue

        try:
            converted_colors[net_name] = parse_color(color_value)
        except ColorError as e:
            logger.warning(f"Skipping invalid color for net '{net_name}': {e}")
            continue

    return converted_colors


def resolve_net_color(
    net_name: str, net_colors_config: dict[str, str]
) -> Optional[str]:
    """Get the color for a given net name, supporting wildcards.

    Args:
        net_name: Name of the net
        net_colors_config: Configuration mapping net patterns to colors

    Returns:
        Hex color string if found, None otherwise
    """
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
        if "*" in pattern or "?" in pattern or "[" in pattern:
            if fnmatch.fnmatch(net_name, pattern):
                return net_colors_config[pattern]

    # No user-defined color found
    return None


def group_nets_by_color(
    net_names: list[str], net_colors: dict[str, str]
) -> tuple[dict[str, list[str]], list[str]]:
    """Group nets by their assigned colors.

    Args:
        net_names: List of all net names
        net_colors: Dictionary mapping net names to colors

    Returns:
        Tuple of (color_groups, default_nets)
        - color_groups: Dict mapping colors to lists of net names
        - default_nets: List of nets with no assigned color
    """
    color_groups: dict[str, list[str]] = {}
    default_nets = []

    for net_name in net_names:
        color = resolve_net_color(net_name, net_colors)
        if color:
            if color not in color_groups:
                color_groups[color] = []
            color_groups[color].append(net_name)
        else:
            default_nets.append(net_name)

    return color_groups, default_nets


def find_copper_color_in_svg(svg_file: Path) -> Optional[str]:
    """Automatically detect copper color in SVG file.

    Args:
        svg_file: Path to SVG file

    Returns:
        Detected copper color as hex string, or None if not found
    """
    try:
        tree = ET.parse(svg_file)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.warning(f"Failed to parse SVG file {svg_file}: {e}")
        return None

    # Look for fill colors in the SVG (both fill attribute and style attribute)
    for elem in root.iter():
        # Check fill attribute
        fill = elem.get("fill")
        if fill and fill not in NON_COPPER_COLORS:
            if re.match(r"^#[0-9A-Fa-f]{6}$", fill):
                return fill.upper()

        # Check style attribute for fill colors
        style = elem.get("style", "")
        if "fill:" in style:
            # Extract fill color from style using regex
            fill_match = re.search(r"fill:\s*#([0-9A-Fa-f]{6})", style)
            if fill_match:
                color = "#" + fill_match.group(1)
                if color.upper() not in NON_COPPER_COLORS:
                    return color.upper()

    return None


def change_svg_color(
    svg_file: Path, old_color: str, new_color: str, output_file: Path
) -> None:
    """Change color in SVG file using string replacement.

    Args:
        svg_file: Input SVG file
        old_color: Color to replace (hex format)
        new_color: New color (hex format)
        output_file: Output SVG file

    Raises:
        ColorError: If color format is invalid or file operations fail
    """
    if not validate_hex_color(old_color):
        msg = f"Invalid old color format: {old_color}"
        raise ColorError(msg)
    if not validate_hex_color(new_color):
        msg = f"Invalid new color format: {new_color}"
        raise ColorError(msg)

    try:
        with open(svg_file) as f:
            content = f.read()
    except OSError as e:
        msg = f"Failed to read SVG file {svg_file}: {e}"
        raise ColorError(msg) from e

    # Replace both hex and RGB formats (case-insensitive)
    old_hex = old_color.lower()
    new_hex = new_color.lower()

    # Convert hex to RGB for additional replacement
    old_rgb_vals = tuple(int(old_color[i : i + 2], 16) for i in (1, 3, 5))
    new_rgb_vals = tuple(int(new_color[i : i + 2], 16) for i in (1, 3, 5))

    old_rgb = f"rgb({old_rgb_vals[0]},{old_rgb_vals[1]},{old_rgb_vals[2]})"
    new_rgb = f"rgb({new_rgb_vals[0]},{new_rgb_vals[1]},{new_rgb_vals[2]})"

    # Perform replacements
    content = content.replace(old_hex, new_hex)
    content = content.replace(old_hex.upper(), new_hex.upper())
    content = content.replace(old_rgb, new_rgb)

    try:
        with open(output_file, "w") as f:
            f.write(content)
    except OSError as e:
        msg = f"Failed to write SVG file {output_file}: {e}"
        raise ColorError(msg) from e


def net_name_to_css_class(net_name: str) -> str:
    """Convert net name to valid CSS class name.

    Args:
        net_name: Net name from PCB

    Returns:
        CSS class name like net-gnd
    """
    css_name = net_name.lower()
    # Replace common problematic characters
    css_name = css_name.replace("/", "-")
    css_name = css_name.replace("\\", "-")
    css_name = css_name.replace("(", "-")
    css_name = css_name.replace(")", "-")
    css_name = css_name.replace(" ", "-")
    css_name = css_name.replace(".", "-")
    css_name = css_name.replace("_", "-")
    css_name = css_name.replace("{", "-")
    css_name = css_name.replace("}", "-")
    css_name = css_name.replace(":", "-")
    css_name = css_name.replace("<", "")
    css_name = css_name.replace(">", "")

    # Remove multiple consecutive dashes
    while "--" in css_name:
        css_name = css_name.replace("--", "-")

    # Remove leading/trailing dashes
    css_name = css_name.strip("-")

    # Ensure it starts with a letter or underscore (CSS requirement)
    if css_name and not (css_name[0].isalpha() or css_name[0] == "_"):
        css_name = "net-" + css_name

    # If empty or only invalid chars, use a default
    if not css_name:
        css_name = "unknown-net"

    return f"net-{css_name}"


def apply_css_class_to_svg(
    svg_file: Path, net_name: str, fallback_color: str, output_file: Path
) -> None:
    """Apply CSS class to net SVG by removing color styles and adding class attributes.

    Args:
        svg_file: Input SVG file
        net_name: Name of the net (used to generate CSS class name)
        fallback_color: Color for the CSS class definition
        output_file: Output SVG file

    Raises:
        ColorError: If color operations fail
    """
    # Parse and validate the color
    try:
        hex_color = parse_color(fallback_color)
    except ColorError as e:
        msg = f"Invalid color: {e}"
        raise ColorError(msg) from e

    # Generate CSS class name
    css_class = net_name_to_css_class(net_name)

    # Try to detect current copper color
    current_color = find_copper_color_in_svg(svg_file)
    if not current_color:
        logger.warning(
            f"Could not detect copper color in {svg_file}, skipping CSS processing"
        )
        # If we can't detect the color, just copy the file without modification
        shutil.copy2(svg_file, output_file)
        return

    # Read SVG content
    try:
        with open(svg_file) as f:
            content = f.read()
    except OSError as e:
        msg = f"Failed to read SVG file {svg_file}: {e}"
        raise ColorError(msg) from e

    old_hex = current_color.lower()
    old_hex_upper = current_color.upper()

    # Convert hex to RGB for additional replacement
    old_rgb_vals = tuple(int(current_color[i : i + 2], 16) for i in (1, 3, 5))
    old_rgb = f"rgb({old_rgb_vals[0]},{old_rgb_vals[1]},{old_rgb_vals[2]})"

    # Remove fill colors from style attributes and add class
    def replace_fill_with_class(match):
        style_content = match.group(1)
        # Remove fill declarations
        style_content = re.sub(r"fill:\s*[^;]+;?", "", style_content)
        # Clean up extra spaces and semicolons
        style_content = re.sub(r";\s*;", ";", style_content)
        style_content = style_content.strip(";").strip()
        return f'style="{style_content}" class="{css_class}"'

    # Find and replace style attributes that contain our color
    content = re.sub(
        r'style="([^"]*(?:fill:\s*(?:'
        + re.escape(old_hex)
        + "|"
        + re.escape(old_hex_upper)
        + "|"
        + re.escape(old_rgb)
        + '))[^"]*)"',
        replace_fill_with_class,
        content,
        flags=re.IGNORECASE,
    )

    # Remove stroke colors from style attributes
    def replace_stroke_with_class(match):
        style_content = match.group(1)
        # Remove stroke declarations
        style_content = re.sub(r"stroke:\s*[^;]+;?", "", style_content)
        # Clean up extra spaces and semicolons
        style_content = re.sub(r";\s*;", ";", style_content)
        style_content = style_content.strip(";").strip()
        # If element already has class, don't add it again
        if "class=" in match.group(0):
            return f'style="{style_content}"'
        return f'style="{style_content}" class="{css_class}"'

    # Find and replace style attributes that contain our stroke color
    content = re.sub(
        r'style="([^"]*(?:stroke:\s*(?:'
        + re.escape(old_hex)
        + "|"
        + re.escape(old_hex_upper)
        + "|"
        + re.escape(old_rgb)
        + '))[^"]*)"',
        replace_stroke_with_class,
        content,
        flags=re.IGNORECASE,
    )

    # Add CSS style section after the <desc> tag
    style_section = f"""<style>
.{css_class} {{
    fill: {hex_color};
    stroke: {hex_color};
}}
</style>"""

    # Insert style after desc tag
    desc_end = content.find("</desc>")
    if desc_end != -1:
        insert_pos = desc_end + len("</desc>")
        content = content[:insert_pos] + "\n" + style_section + content[insert_pos:]

    try:
        with open(output_file, "w") as f:
            f.write(content)
    except OSError as e:
        msg = f"Failed to write SVG file {output_file}: {e}"
        raise ColorError(msg) from e


def apply_color_to_svg(svg_file: Path, net_color: str, output_file: Path) -> None:
    """Apply color to net SVG by detecting and replacing copper color.

    Args:
        svg_file: Input SVG file
        net_color: Color to apply (any supported format)
        output_file: Output SVG file

    Raises:
        ColorError: If color operations fail
    """
    # Parse and validate the target color
    try:
        hex_color = parse_color(net_color)
    except ColorError as e:
        msg = f"Invalid net color: {e}"
        raise ColorError(msg) from e

    # Try to detect current copper color
    current_color = find_copper_color_in_svg(svg_file)
    if not current_color:
        logger.warning(
            f"Could not detect copper color in {svg_file}, skipping CSS processing"
        )
        # If we can't detect the color, just copy the file without modification
        shutil.copy2(svg_file, output_file)
        return

    # Apply the color change
    change_svg_color(svg_file, current_color, hex_color, output_file)
