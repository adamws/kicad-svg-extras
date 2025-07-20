# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Comprehensive tests for svg_processor.py module."""

import xml.etree.ElementTree as ET

import pytest

from kicad_svg_extras.svg_processor import (
    add_background_to_svg,
    extract_css_styles,
    merge_css_styles,
    merge_svg_files,
)


def assert_valid_svg(svg_content: str) -> ET.Element:
    """Assert that the content is valid XML/SVG and return the root element.

    This helper function validates that all SVG output from svg_processor functions
    is well-formed XML and has the correct root element.

    Args:
        svg_content: SVG content as string

    Returns:
        Root element of parsed SVG

    Raises:
        AssertionError: If content is not valid XML or not an SVG
    """
    try:
        root = ET.fromstring(svg_content)
        # Additional SVG-specific validation
        assert root.tag.endswith(
            "svg"
        ), f"Root element should be 'svg', got '{root.tag}'"
        return root
    except ET.ParseError as e:
        msg = f"Invalid XML/SVG content: {e}"
        raise AssertionError(msg) from e


class TestExtractCssStyles:
    """Test extract_css_styles function."""

    @pytest.mark.parametrize(
        "svg_content,expected",
        [
            # Basic style extraction
            (
                "<svg><style>.net-clk { fill: #FF0000; }</style></svg>",
                ".net-clk { fill: #FF0000; }",
            ),
            # Style with multiple rules
            (
                "<svg><style>.net-clk { fill: #FF0000; }\n.net-gnd { fill: #00FF00; }</style></svg>",  # noqa: E501
                ".net-clk { fill: #FF0000; }\n.net-gnd { fill: #00FF00; }",
            ),
            # Style with attributes
            (
                '<svg><style type="text/css">.net { fill: blue; }</style></svg>',
                ".net { fill: blue; }",
            ),
            # Multiple style tags (should extract first)
            (
                "<svg><style>.a { fill: red; }</style><style>.b { fill: blue; }</style></svg>",  # noqa: E501
                ".a { fill: red; }",
            ),
            # Style with whitespace
            (
                "<svg><style>\n  .net {\n    fill: #123456;\n    stroke: #654321;\n  }\n</style></svg>",  # noqa: E501
                ".net {\n    fill: #123456;\n    stroke: #654321;\n  }",
            ),
            # No style tag
            ("<svg><g fill='red'></g></svg>", ""),
            # Empty style tag
            ("<svg><style></style></svg>", ""),
            # Style with only whitespace
            ("<svg><style>   \n\t  </style></svg>", ""),
        ],
    )
    def test_extract_css_styles(self, svg_content, expected):
        """Test CSS extraction from various SVG content."""
        result = extract_css_styles(svg_content)
        assert result == expected

    def test_extract_complex_css(self):
        """Test extraction of complex CSS with comments and media queries."""
        svg_content = """<svg>
        <style>
        /* CSS comment */
        .net-clk {
            fill: #FF0000;
            stroke: #FF0000;
        }

        @media (max-width: 600px) {
            .net-clk { fill: blue; }
        }
        </style>
        </svg>"""

        result = extract_css_styles(svg_content)
        assert "/* CSS comment */" in result
        assert ".net-clk" in result
        assert "@media" in result
        assert "#FF0000" in result


class TestMergeCssStyles:
    """Test merge_css_styles function."""

    def test_empty_styles_list(self):
        """Test merging empty CSS styles list."""
        result = merge_css_styles([])
        assert result == ""

    def test_single_css_style(self):
        """Test merging single CSS style."""
        css = ".net-clk { fill: #FF0000; }"
        result = merge_css_styles([css])
        assert result == css

    @pytest.mark.parametrize(
        "css_styles,expected_rules",
        [
            # Basic merging without duplicates
            (
                [".net-clk { fill: #FF0000; }", ".net-gnd { fill: #00FF00; }"],
                [".net-clk { fill: #FF0000; }", ".net-gnd { fill: #00FF00; }"],
            ),
            # Remove exact duplicates
            (
                [".net-clk { fill: #FF0000; }", ".net-clk { fill: #FF0000; }"],
                [".net-clk { fill: #FF0000; }"],
            ),
            # Multiple rules in single style
            (
                [".net-clk { fill: #FF0000; } .net-gnd { fill: #00FF00; }"],
                [".net-clk { fill: #FF0000; }", ".net-gnd { fill: #00FF00; }"],
            ),
            # Empty strings filtered out
            (
                [
                    "",
                    ".net-clk { fill: #FF0000; }",
                    "   ",
                    ".net-gnd { fill: #00FF00; }",
                ],
                [".net-clk { fill: #FF0000; }", ".net-gnd { fill: #00FF00; }"],
            ),
        ],
    )
    def test_merge_multiple_styles(self, css_styles, expected_rules):
        """Test merging multiple CSS styles."""
        result = merge_css_styles(css_styles)

        # Verify all expected rules are present
        for rule in expected_rules:
            assert rule in result

        # Verify no duplicates (count newlines + 1 should equal expected rules)
        result_lines = [line.strip() for line in result.split("\n") if line.strip()]
        assert len(result_lines) == len(expected_rules)

    def test_complex_css_rules(self):
        """Test merging complex CSS rules with nested selectors."""
        css_styles = [
            """.net-clk {
                fill: #FF0000;
                stroke: #FF0000;
            }""",
            """.net-gnd {
                fill: #00FF00;
            }
            .net-power {
                fill: #0000FF;
                stroke-width: 2px;
            }""",
        ]

        result = merge_css_styles(css_styles)

        # Should contain all class selectors
        assert ".net-clk" in result
        assert ".net-gnd" in result
        assert ".net-power" in result

        # Should contain all properties
        assert "#FF0000" in result
        assert "#00FF00" in result
        assert "#0000FF" in result
        assert "stroke-width: 2px" in result


class TestMergeSvgFiles:
    """Test merge_svg_files function."""

    def test_empty_file_list(self, tmp_path):
        """Test error when no files to merge."""
        output_file = tmp_path / "output.svg"

        with pytest.raises(ValueError, match="No SVG files to merge"):
            merge_svg_files([], output_file)

    def test_dimension_validation_mismatch(self, tmp_path):
        """Test error when SVG files have mismatched dimensions."""
        # Create two SVG files with different dimensions
        svg1 = tmp_path / "file1.svg"
        svg2 = tmp_path / "file2.svg"
        output_file = tmp_path / "output.svg"

        svg1_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
            <g><circle r="5"/></g>
        </svg>"""

        svg2_content = """<?xml version="1.0"?>
        <svg width="200mm" height="100mm" viewBox="0 0 200 100">
            <g><rect width="10" height="10"/></g>
        </svg>"""

        with open(svg1, "w") as f:
            f.write(svg1_content)
        with open(svg2, "w") as f:
            f.write(svg2_content)

        with pytest.raises(ValueError, match="SVG dimension mismatch"):
            merge_svg_files([svg1, svg2], output_file)

    def test_successful_merge_without_css(self, tmp_path):
        """Test successful merging of SVG files without CSS."""
        svg1 = tmp_path / "file1.svg"
        svg2 = tmp_path / "file2.svg"
        output_file = tmp_path / "output.svg"

        svg1_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
            <g fill="red"><circle cx="50" cy="50" r="5"/></g>
        </svg>"""

        svg2_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
            <g fill="blue"><rect x="10" y="10" width="10" height="10"/></g>
        </svg>"""

        with open(svg1, "w") as f:
            f.write(svg1_content)
        with open(svg2, "w") as f:
            f.write(svg2_content)

        merge_svg_files([svg1, svg2], output_file)

        # Verify output file exists and contains expected content
        assert output_file.exists()

        with open(output_file) as f:
            result = f.read()

        assert_valid_svg(result)

        assert 'width="100mm" height="100mm" viewBox="0 0 100 100"' in result
        assert '<circle cx="50" cy="50" r="5"/>' in result
        assert '<rect x="10" y="10" width="10" height="10"/>' in result
        assert 'fill="red"' in result
        assert 'fill="blue"' in result

    def test_successful_merge_with_css(self, tmp_path):
        """Test successful merging of SVG files with CSS styles."""
        svg1 = tmp_path / "file1.svg"
        svg2 = tmp_path / "file2.svg"
        output_file = tmp_path / "output.svg"

        svg1_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
        <style>.net-clk { fill: #FF0000; }</style>
        <g class="net-clk"><circle cx="50" cy="50" r="5"/></g>
        </svg>"""

        svg2_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
        <style>.net-gnd { fill: #00FF00; }</style>
        <g class="net-gnd"><rect x="10" y="10" width="10" height="10"/></g>
        </svg>"""

        with open(svg1, "w") as f:
            f.write(svg1_content)
        with open(svg2, "w") as f:
            f.write(svg2_content)

        merge_svg_files([svg1, svg2], output_file)

        # Verify output file contains merged CSS and content
        with open(output_file) as f:
            result = f.read()

        assert_valid_svg(result)

        assert "<style>" in result
        assert ".net-clk { fill: #FF0000; }" in result
        assert ".net-gnd { fill: #00FF00; }" in result
        assert 'class="net-clk"' in result
        assert 'class="net-gnd"' in result

    def test_merge_with_base_svg(self, tmp_path):
        """Test merging with a base SVG file."""
        base_svg = tmp_path / "base.svg"
        svg1 = tmp_path / "file1.svg"
        output_file = tmp_path / "output.svg"

        base_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
            <g fill="gray"><rect x="0" y="0" width="100" height="100"/></g>
        </svg>"""

        svg1_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
            <g fill="red"><circle cx="50" cy="50" r="5"/></g>
        </svg>"""

        with open(base_svg, "w") as f:
            f.write(base_content)
        with open(svg1, "w") as f:
            f.write(svg1_content)

        merge_svg_files([svg1], output_file, base_svg=base_svg)

        # Verify base SVG dimensions are used for validation
        assert output_file.exists()

        with open(output_file) as f:
            result = f.read()

        assert_valid_svg(result)

        assert 'width="100mm" height="100mm" viewBox="0 0 100 100"' in result
        assert '<circle cx="50" cy="50" r="5"/>' in result

    def test_add_background_to_merged_svg(self, tmp_path):
        """Test adding background to a merged SVG file."""
        svg1 = tmp_path / "file1.svg"
        svg2 = tmp_path / "file2.svg"
        output_file = tmp_path / "output.svg"

        svg1_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
            <g fill="red"><circle cx="25" cy="25" r="5"/></g>
        </svg>"""

        svg2_content = """<?xml version="1.0"?>
        <svg width="100mm" height="100mm" viewBox="0 0 100 100">
            <g fill="blue"><circle cx="75" cy="75" r="5"/></g>
        </svg>"""

        with open(svg1, "w") as f:
            f.write(svg1_content)
        with open(svg2, "w") as f:
            f.write(svg2_content)

        # First merge the SVGs
        merge_svg_files([svg1, svg2], output_file)

        # Then add background to the merged result
        add_background_to_svg(output_file, "#282A36")

        with open(output_file) as f:
            result = f.read()

        assert_valid_svg(result)

        # Should contain both circles and background
        assert 'cx="25" cy="25" r="5"' in result
        assert 'cx="75" cy="75" r="5"' in result
        assert 'fill="#282A36"' in result
        assert "<rect" in result

    def test_no_valid_files(self, tmp_path):
        """Test error when no valid SVG files are found."""
        nonexistent_file = tmp_path / "nonexistent.svg"
        output_file = tmp_path / "output.svg"

        with pytest.raises(ValueError, match="No valid SVG files found for merging"):
            merge_svg_files([nonexistent_file], output_file)


class TestAddBackgroundToSvg:
    """Test add_background_to_svg function."""

    def test_add_background_with_viewbox(self, tmp_path):
        """Test adding background using viewBox dimensions."""
        svg_file = tmp_path / "test.svg"
        svg_content = """<?xml version="1.0"?>
        <svg width="100mm" height="50mm" viewBox="0 0 100 50" xmlns="http://www.w3.org/2000/svg">
            <desc>Test SVG</desc>
            <circle cx="50" cy="25" r="10"/>
        </svg>"""

        with open(svg_file, "w") as f:
            f.write(svg_content)

        add_background_to_svg(svg_file, "#123456")

        # Read and validate the modified SVG
        with open(svg_file) as f:
            result = f.read()
        root = assert_valid_svg(result)

        # Parse the modified SVG for detailed validation
        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Find the background rectangle
        rect = root.find(".//{http://www.w3.org/2000/svg}rect")
        assert rect is not None
        assert rect.attrib["x"] == "0.0"
        assert rect.attrib["y"] == "0.0"
        assert rect.attrib["width"] == "100.0"
        assert rect.attrib["height"] == "50.0"
        assert rect.attrib["fill"] == "#123456"

    def test_add_background_without_viewbox(self, tmp_path):
        """Test adding background using width/height attributes."""
        svg_file = tmp_path / "test.svg"
        svg_content = """<?xml version="1.0"?>
        <svg width="200px" height="100px" xmlns="http://www.w3.org/2000/svg">
            <desc>Test SVG</desc>
            <circle cx="50" cy="25" r="10"/>
        </svg>"""

        with open(svg_file, "w") as f:
            f.write(svg_content)

        add_background_to_svg(svg_file, "#ABCDEF")

        # Read and validate the modified SVG
        with open(svg_file) as f:
            result = f.read()
        assert_valid_svg(result)

        # Parse the modified SVG for detailed validation
        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Find the background rectangle
        rect = root.find(".//{http://www.w3.org/2000/svg}rect")
        assert rect is not None
        assert rect.attrib["x"] == "0"
        assert rect.attrib["y"] == "0"
        assert rect.attrib["width"] == "200.0"
        assert rect.attrib["height"] == "100.0"
        assert rect.attrib["fill"] == "#ABCDEF"

    @pytest.mark.parametrize(
        "width,height,expected_width,expected_height",
        [
            ("100mm", "50mm", "100.0", "50.0"),
            ("200px", "100px", "200.0", "100.0"),
            ("5cm", "3cm", "5.0", "3.0"),
            ("72pt", "36pt", "72.0", "36.0"),
            ("2in", "1in", "2.0", "1.0"),
            ("150", "75", "150.0", "75.0"),  # No units
        ],
    )
    def test_unit_stripping(
        self, tmp_path, width, height, expected_width, expected_height
    ):
        """Test that various units are properly stripped from dimensions."""
        svg_file = tmp_path / "test.svg"
        svg_content = f"""<?xml version="1.0"?>
        <svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <desc>Test SVG</desc>
        </svg>"""

        with open(svg_file, "w") as f:
            f.write(svg_content)

        add_background_to_svg(svg_file, "#FF0000")

        # Validate the modified SVG
        with open(svg_file) as f:
            result = f.read()
        assert_valid_svg(result)

        tree = ET.parse(svg_file)
        root = tree.getroot()
        rect = root.find(".//{http://www.w3.org/2000/svg}rect")

        assert rect.attrib["width"] == expected_width
        assert rect.attrib["height"] == expected_height

    def test_background_position_after_desc(self, tmp_path):
        """Test that background rectangle is inserted after desc element."""
        svg_file = tmp_path / "test.svg"
        svg_content = """<?xml version="1.0"?>
        <svg width="100mm" height="50mm" viewBox="0 0 100 50" xmlns="http://www.w3.org/2000/svg">
            <title>Title</title>
            <desc>Description</desc>
            <g id="content">
                <circle cx="50" cy="25" r="10"/>
            </g>
        </svg>"""

        with open(svg_file, "w") as f:
            f.write(svg_content)

        add_background_to_svg(svg_file, "#BACKGROUND")

        # Validate the modified SVG
        with open(svg_file) as f:
            result = f.read()
        assert_valid_svg(result)

        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Get all children to check order
        children = list(root)

        # Find indices of key elements
        title_idx = next(
            i for i, child in enumerate(children) if child.tag.endswith("title")
        )
        desc_idx = next(
            i for i, child in enumerate(children) if child.tag.endswith("desc")
        )
        rect_idx = next(
            i for i, child in enumerate(children) if child.tag.endswith("rect")
        )
        group_idx = next(
            i for i, child in enumerate(children) if child.tag.endswith("g")
        )

        # Background rect should be right after desc and before other content
        assert title_idx < desc_idx < rect_idx < group_idx

    def test_fallback_dimensions(self, tmp_path):
        """Test fallback behavior when no viewBox or valid dimensions."""
        svg_file = tmp_path / "test.svg"
        svg_content = """<?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg">
            <desc>Test SVG</desc>
        </svg>"""

        with open(svg_file, "w") as f:
            f.write(svg_content)

        add_background_to_svg(svg_file, "#DEFAULT")

        # Validate the modified SVG
        with open(svg_file) as f:
            result = f.read()
        assert_valid_svg(result)

        tree = ET.parse(svg_file)
        root = tree.getroot()
        rect = root.find(".//{http://www.w3.org/2000/svg}rect")

        # Should use fallback dimensions
        assert rect.attrib["width"] == "100.0"
        assert rect.attrib["height"] == "100.0"
        assert rect.attrib["fill"] == "#DEFAULT"

    def test_svg_without_desc(self, tmp_path):
        """Test behavior when SVG has no desc element."""
        svg_file = tmp_path / "test.svg"
        svg_content = """<?xml version="1.0"?>
        <svg width="100mm" height="50mm" viewBox="0 0 100 50" xmlns="http://www.w3.org/2000/svg">
            <circle cx="50" cy="25" r="10"/>
        </svg>"""

        with open(svg_file, "w") as f:
            f.write(svg_content)

        # Should not raise error, but also should not add background
        add_background_to_svg(svg_file, "#123456")

        # Validate the SVG is still valid
        with open(svg_file) as f:
            result = f.read()
        assert_valid_svg(result)

        tree = ET.parse(svg_file)
        root = tree.getroot()

        # Should not have added a rectangle
        rect = root.find(".//{http://www.w3.org/2000/svg}rect")
        assert rect is None
