# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""SVG processing utilities for color modification and merging."""

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from kicad_svg_extras.colors import DEFAULT_BACKGROUND_DARK

logger = logging.getLogger(__name__)

# SVG namespace
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def _parse_svg_number(value: str) -> float:
    """Parse SVG numeric value, handling units and percentages.

    Args:
        value: SVG attribute value (e.g., '100', '10.5mm', '50%')

    Returns:
        Numeric value (units stripped, percentages not supported)
    """
    if not value:
        return 0.0

    # Remove common SVG units - we assume all are in the same coordinate system
    value = re.sub(r"(px|mm|cm|pt|pc|in|em|ex|%)", "", value.strip())

    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_transform(transform_attr: str) -> tuple[float, float, float, float]:
    """Parse SVG transform attribute and return bounding box adjustments.

    Args:
        transform_attr: SVG transform attribute value

    Returns:
        Tuple of (min_x_offset, min_y_offset, max_x_offset, max_y_offset)
    """
    if not transform_attr:
        return (0.0, 0.0, 0.0, 0.0)

    # Simple implementation - handle translate() which is most common in KiCad SVGs
    translate_match = re.search(
        r"translate\(\s*(-?[\d.]+)(?:\s*,\s*(-?[\d.]+))?\s*\)", transform_attr
    )
    if translate_match:
        tx = float(translate_match.group(1))
        ty = float(translate_match.group(2)) if translate_match.group(2) else 0.0
        return (tx, ty, tx, ty)

    # For other transforms, return no offset (conservative approach)
    return (0.0, 0.0, 0.0, 0.0)


def _get_element_bounds(
    element: ET.Element,
) -> Optional[tuple[float, float, float, float]]:
    """Calculate bounding box for a single SVG element.

    Args:
        element: SVG element to analyze

    Returns:
        Tuple of (min_x, max_x, min_y, max_y) or None if element has no bounds
    """
    tag = (
        element.tag.replace(f"{{{SVG_NS}}}", "")
        if SVG_NS in element.tag
        else element.tag
    )

    # Handle different element types
    if tag == "rect":
        x = _parse_svg_number(element.get("x", "0"))
        y = _parse_svg_number(element.get("y", "0"))
        width = _parse_svg_number(element.get("width", "0"))
        height = _parse_svg_number(element.get("height", "0"))
        return (x, x + width, y, y + height)

    elif tag == "circle":
        cx = _parse_svg_number(element.get("cx", "0"))
        cy = _parse_svg_number(element.get("cy", "0"))
        r = _parse_svg_number(element.get("r", "0"))
        return (cx - r, cx + r, cy - r, cy + r)

    elif tag == "ellipse":
        cx = _parse_svg_number(element.get("cx", "0"))
        cy = _parse_svg_number(element.get("cy", "0"))
        rx = _parse_svg_number(element.get("rx", "0"))
        ry = _parse_svg_number(element.get("ry", "0"))
        return (cx - rx, cx + rx, cy - ry, cy + ry)

    elif tag == "line":
        x1 = _parse_svg_number(element.get("x1", "0"))
        y1 = _parse_svg_number(element.get("y1", "0"))
        x2 = _parse_svg_number(element.get("x2", "0"))
        y2 = _parse_svg_number(element.get("y2", "0"))
        return (min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2))

    elif tag == "path":
        # Parse path data for bounds (simplified approach)
        d = element.get("d", "")
        if not d:
            return None

        # Extract all coordinate numbers from path data
        coords = re.findall(r"-?[\d.]+", d)
        min_coords_required = 2
        if len(coords) < min_coords_required:
            return None

        try:
            coords = [float(c) for c in coords]
            x_coords = coords[::2]  # Even indices are x coordinates
            y_coords = coords[1::2]  # Odd indices are y coordinates

            if x_coords and y_coords:
                return (min(x_coords), max(x_coords), min(y_coords), max(y_coords))
        except (ValueError, IndexError):
            pass

    elif tag in ["text", "tspan"]:
        # For text elements, use position as point
        x = _parse_svg_number(element.get("x", "0"))
        y = _parse_svg_number(element.get("y", "0"))
        # Rough estimate: assume text is 10 units wide and high
        return (x, x + 10, y - 5, y + 5)

    # Element type not handled or no position info
    return None


def calculate_svg_bounding_box(
    svg_file: Path, margin: float = 1.0
) -> Optional[tuple[float, float, float, float]]:
    """Calculate the bounding box of all drawable content in an SVG file.

    Args:
        svg_file: Path to SVG file to analyze
        margin: Margin to add around content bounds (in SVG units, typically mm)

    Returns:
        Tuple of (min_x, max_x, min_y, max_y) including margin, or None if no content
    """
    try:
        tree = ET.parse(svg_file)
        root = tree.getroot()

        bounds_list = []

        def collect_bounds(
            element: ET.Element, transform_stack: Optional[list] = None
        ) -> None:
            """Recursively collect bounds from all elements."""
            if transform_stack is None:
                transform_stack = []

            # Get transform for this element
            current_transform = element.get("transform", "")
            if current_transform:
                transform_stack.append(_parse_transform(current_transform))

            # Calculate bounds for this element
            element_bounds = _get_element_bounds(element)
            if element_bounds is not None:
                min_x, max_x, min_y, max_y = element_bounds

                # Apply all transforms in stack
                for tx_offset, ty_offset, _, _ in transform_stack:
                    min_x += tx_offset
                    max_x += tx_offset
                    min_y += ty_offset
                    max_y += ty_offset

                bounds_list.append((min_x, max_x, min_y, max_y))

            # Recurse into child elements
            for child in element:
                collect_bounds(child, transform_stack.copy())

        # Collect bounds from all elements
        collect_bounds(root)

        if not bounds_list:
            logger.debug(f"No drawable content found in {svg_file}")
            return None

        # Calculate overall bounding box
        min_x = min(bounds[0] for bounds in bounds_list)
        max_x = max(bounds[1] for bounds in bounds_list)
        min_y = min(bounds[2] for bounds in bounds_list)
        max_y = max(bounds[3] for bounds in bounds_list)

        # Add margin
        min_x -= margin
        max_x += margin
        min_y -= margin
        max_y += margin

        logger.debug(
            f"Calculated SVG bounds: "
            f"({min_x:.3f}, {max_x:.3f}, {min_y:.3f}, {max_y:.3f})"
        )
        return (min_x, max_x, min_y, max_y)

    except Exception as e:
        logger.warning(f"Failed to calculate SVG bounding box for {svg_file}: {e}")
        return None


def extract_css_styles(svg_content: str) -> str:
    """Extract CSS styles from SVG content.

    Args:
        svg_content: SVG file content as string

    Returns:
        CSS content or empty string if no styles found
    """
    # Extract content between <style> tags
    style_match = re.search(r"<style[^>]*>(.*?)</style>", svg_content, re.DOTALL)
    if style_match:
        return style_match.group(1).strip()
    return ""


def merge_css_styles(css_styles: list[str]) -> str:
    """Merge multiple CSS style blocks into one.

    Args:
        css_styles: List of CSS content strings

    Returns:
        Merged CSS content
    """
    if not css_styles:
        return ""

    # Combine all CSS rules, removing duplicates
    all_rules = []
    seen_rules = set()

    for css_content in css_styles:
        if not css_content.strip():
            continue

        # Split into individual rules (simple approach)
        rules = re.findall(r"[^{}]+\{[^{}]*\}", css_content)
        for raw_rule in rules:
            rule = raw_rule.strip()
            if rule and rule not in seen_rules:
                all_rules.append(rule)
                seen_rules.add(rule)

    return "\n".join(all_rules)


def merge_svg_files(
    svg_files: list[Path], output_file: Path, base_svg: Optional[Path] = None
) -> None:
    """Merge multiple SVG files into one."""
    if not svg_files:
        msg = "No SVG files to merge"
        raise ValueError(msg)

    # Validate that all SVG files have identical dimensions and viewBox
    all_files = []
    if base_svg and base_svg.exists():
        all_files.append(base_svg)
    all_files.extend(svg_files)

    # Get dimensions from first file as reference
    reference_width = None
    reference_height = None
    reference_viewbox = None

    for svg_file in all_files:
        if not svg_file.exists():
            continue

        tree = ET.parse(svg_file)
        root = tree.getroot()

        width = root.attrib.get("width")
        height = root.attrib.get("height")
        viewbox = root.attrib.get("viewBox")

        if reference_width is None:
            # First file - use as reference
            reference_width = width
            reference_height = height
            reference_viewbox = viewbox
        # Validate all subsequent files match
        elif (
            width != reference_width
            or height != reference_height
            or viewbox != reference_viewbox
        ):
            msg = (
                f"SVG dimension mismatch in {svg_file}: "
                f"expected width={reference_width}, height={reference_height}, "
                f"viewBox={reference_viewbox} but got width={width}, "
                f"height={height}, viewBox={viewbox}"
            )
            raise ValueError(msg)

    if reference_viewbox is None:
        msg = "No valid SVG files found for merging"
        raise ValueError(msg)

    # Use simple string-based approach to avoid XML namespace issues
    # Extract CSS styles from all SVG files
    css_styles = []
    for svg_file in svg_files:
        if not svg_file.exists():
            continue

        with open(svg_file) as f:
            content = f.read()

        css_style = extract_css_styles(content)
        if css_style:
            css_styles.append(css_style)

    # Merge CSS styles
    merged_css = merge_css_styles(css_styles)

    # Start building SVG content using reference dimensions
    svg_content = f"""<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg
xmlns:svg="http://www.w3.org/2000/svg"
xmlns="http://www.w3.org/2000/svg"
xmlns:xlink="http://www.w3.org/1999/xlink"
version="1.1"
width="{reference_width}" height="{reference_height}" viewBox="{reference_viewbox}">
<title>Merged SVG with per-net colors</title>
<desc>Generated by net_colored_svg tool</desc>
"""

    # Add merged CSS styles if any
    if merged_css:
        svg_content += f"<style>\n{merged_css}\n</style>\n"

    # Extract content from all SVG files
    for svg_file in svg_files:
        if not svg_file.exists():
            continue

        with open(svg_file) as f:
            content = f.read()

        # Extract groups and elements between <svg> and </svg>
        start = content.find("<g")
        end = content.rfind("</g>") + 4

        if start != -1 and end != -1:
            group_content = content[start:end]
            # Skip background rectangles and style tags
            if (
                f'fill="{DEFAULT_BACKGROUND_DARK}"' not in group_content
                and "<style>" not in group_content
            ):
                svg_content += group_content + "\n"

    svg_content += "</svg>"

    # Write merged SVG
    with open(output_file, "w") as f:
        f.write(svg_content)


def add_background_to_svg(svg_file: Path, background_color: str) -> None:
    """Add background to SVG file."""
    tree = ET.parse(svg_file)
    root = tree.getroot()

    desc = root.find(f".//{{{SVG_NS}}}desc")
    if desc is not None:
        # Get viewBox dimensions instead of width/height with units
        viewbox = root.attrib.get("viewBox")
        if viewbox:
            x, y, width, height = map(float, viewbox.split())
        else:
            # Fallback: strip units from width/height
            svg_w = root.attrib.get("width", "100")
            svg_h = root.attrib.get("height", "100")
            # Remove common units
            for unit in ["cm", "mm", "px", "pt", "in"]:
                svg_w = svg_w.replace(unit, "")
                svg_h = svg_h.replace(unit, "")
            x, y = 0, 0
            width = float(svg_w) if svg_w else 100
            height = float(svg_h) if svg_h else 100

        parent = root
        children = list(parent)
        desc_index = children.index(desc)

        # Add background rectangle using viewBox coordinates
        rect = ET.Element(
            "rect",
            x=str(x),
            y=str(y),
            width=str(width),
            height=str(height),
            fill=background_color,
        )
        parent.insert(desc_index + 1, rect)

        tree.write(svg_file, encoding="unicode")


def fit_svg_to_content(svg_file: Path, margin: float = 1.0) -> None:
    """Fit SVG to content by updating viewBox and dimensions to content bounds.

    Args:
        svg_file: Path to SVG file to process in-place
        margin: Margin to add around content bounds (in SVG units, typically mm)

    Raises:
        RuntimeError: If SVG processing fails
    """
    # Calculate content bounding box
    bounds = calculate_svg_bounding_box(svg_file, margin)

    if bounds is None:
        logger.warning(
            f"No drawable content found in {svg_file}, skipping fit-to-content"
        )
        return

    min_x, max_x, min_y, max_y = bounds
    width = max_x - min_x
    height = max_y - min_y

    # Ensure minimum dimensions to avoid tiny/invisible SVGs
    min_size = 5.0  # 5mm minimum
    if width < min_size:
        center_x = (min_x + max_x) / 2
        min_x = center_x - min_size / 2
        max_x = center_x + min_size / 2
        width = min_size

    if height < min_size:
        center_y = (min_y + max_y) / 2
        min_y = center_y - min_size / 2
        max_y = center_y + min_size / 2
        height = min_size

    try:
        # Update SVG file with new dimensions
        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Update viewBox and dimensions
        root.set("viewBox", f"{min_x} {min_y} {width} {height}")
        root.set("width", f"{width}mm")
        root.set("height", f"{height}mm")

        # Write back to file
        tree.write(svg_file, encoding="unicode")

        logger.info(f"Fitted SVG to content: {svg_file} -> {width:.3f}x{height:.3f}mm")

    except Exception as e:
        msg = f"Failed to update SVG dimensions: {e}"
        raise RuntimeError(msg) from e
