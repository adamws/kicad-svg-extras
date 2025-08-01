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
    svg_files: list[Path],
    output_file: Path,
    base_svg: Optional[Path] = None,
    forced_width: Optional[str] = None,
    forced_height: Optional[str] = None,
    forced_viewbox: Optional[str] = None,
) -> None:
    """Merge multiple SVG files into one.

    Args:
        svg_files: List of SVG files to merge
        output_file: Output file path
        base_svg: Optional base SVG file
        forced_width: Override width (e.g., "10mm") when KiCad page size limits
            are hit
        forced_height: Override height (e.g., "5mm") when KiCad page size limits
            are hit
        forced_viewbox: Override viewBox (e.g., "0 0 10 5") when KiCad page size
            limits are hit
    """
    if not svg_files:
        msg = "No SVG files to merge"
        raise ValueError(msg)

    logger.debug(f"Starting merge of {len(svg_files)} SVG files into {output_file}")
    logger.debug("SVG merge order:")
    for i, svg_file in enumerate(svg_files):
        logger.debug(f"  {i+1:2d}. {svg_file.name}")
    if base_svg:
        logger.debug(f"  Base SVG: {base_svg.name}")

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

    # Use forced dimensions if provided, otherwise use reference dimensions
    final_width = forced_width if forced_width else reference_width
    final_height = forced_height if forced_height else reference_height
    final_viewbox = forced_viewbox if forced_viewbox else reference_viewbox

    if forced_width or forced_height or forced_viewbox:
        logger.debug(
            f"Using forced dimensions: {final_width}x{final_height} "
            f"viewBox={final_viewbox} (reference was {reference_width}x"
            f"{reference_height} viewBox={reference_viewbox})"
        )

    # Start building SVG content using final dimensions
    svg_content = f"""<?xml version="1.0" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg
xmlns:svg="http://www.w3.org/2000/svg"
xmlns="http://www.w3.org/2000/svg"
xmlns:xlink="http://www.w3.org/1999/xlink"
version="1.1"
width="{final_width}" height="{final_height}" viewBox="{final_viewbox}">
<title>Merged SVG with per-net colors</title>
<desc>Generated by net_colored_svg tool</desc>
"""

    # Add merged CSS styles if any
    if merged_css:
        svg_content += f"<style>\n{merged_css}\n</style>\n"

    # Extract content from all SVG files
    for i, svg_file in enumerate(svg_files):
        if not svg_file.exists():
            logger.debug(f"  Skipping non-existent file: {svg_file.name}")
            continue

        logger.debug(f"  Merging layer {i+1}/{len(svg_files)}: {svg_file.name}")

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
                logger.debug(
                    f"    Added content from {svg_file.name} "
                    f"({len(group_content)} chars)"
                )
                svg_content += group_content + "\n"
            else:
                logger.debug(
                    f"    Skipped background/style content from {svg_file.name}"
                )
        else:
            logger.debug(f"    No valid <g> content found in {svg_file.name}")

    svg_content += "</svg>"

    # Write merged SVG
    with open(output_file, "w") as f:
        f.write(svg_content)

    logger.debug(f"Successfully merged {len(svg_files)} SVG files into {output_file}")
    logger.debug(f"Final merged SVG size: {len(svg_content):,} characters")


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


def remove_empty_groups(svg_file: Path) -> None:
    """Remove empty groups from an SVG file.

    KiCad's plotter creates many empty groups that are not needed and can be
    safely removed to clean up the output.
    """
    tree = ET.parse(svg_file)
    root = tree.getroot()

    def _remove_empty_groups(root) -> None:
        for elem in root.findall(f".//{{{SVG_NS}}}g"):
            if len(elem) == 0:
                root.remove(elem)
        for child in root:
            _remove_empty_groups(child)

    _remove_empty_groups(root)
    tree.write(svg_file, encoding="unicode")
