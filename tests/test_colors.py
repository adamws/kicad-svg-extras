# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Comprehensive tests for colors.py module."""

import json

import pytest

from kicad_svg_extras.colors import (
    ColorError,
    apply_color_to_svg,
    apply_css_class_to_svg,
    change_svg_color,
    find_copper_color_in_svg,
    group_nets_by_color,
    load_color_config,
    net_name_to_css_class,
    parse_color,
    resolve_net_color,
    validate_hex_color,
)

pytestmark = pytest.mark.unit

# SVG Content Templates
SVG_WITH_COPPER_COLOR = """<svg xmlns="http://www.w3.org/2000/svg">
<desc>Generated by KiCad</desc>
<g style="fill:#B28C00">
  <path d="M10,10 L20,20"/>
</g>
</svg>"""

SVG_WITH_COPPER_FILL_AND_STROKE = """<svg xmlns="http://www.w3.org/2000/svg">
<desc>Generated by KiCad</desc>
<g style="fill:#B28C00;stroke:#B28C00">
  <path d="M10,10 L20,20"/>
</g>
</svg>"""

SVG_WITH_COPPER_AND_STROKE_WIDTH = """<svg xmlns="http://www.w3.org/2000/svg">
<desc>Generated by KiCad</desc>
<g style="fill:#B28C00;stroke:#B28C00;stroke-width:0.1">
  <path d="M10,10 L20,20"/>
</g>
</svg>"""

SVG_WITHOUT_COPPER_COLOR = """<svg xmlns="http://www.w3.org/2000/svg">
<desc>Generated by KiCad</desc>
<g style="fill:#000000">
  <path d="M10,10 L20,20"/>
</g>
</svg>"""

SVG_MINIMAL = "<svg></svg>"

SVG_WITH_HEX_COLORS = """<svg xmlns="http://www.w3.org/2000/svg">
  <rect fill="#FF0000" width="10" height="10"/>
  <circle fill="#ff0000" r="5"/>
</svg>"""

SVG_WITH_RGB_COLOR = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg">
    <rect style="fill:rgb(255,0,0)" width="10" height="10"/>
</svg>"""

SVG_WITH_MIXED_RED_COLORS = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg">
    <rect fill="#FF0000" width="10" height="10"/>
    <circle style="fill:#FF0000" r="5"/>
    <path stroke="#ff0000" d="M0,0 L10,10"/>
</svg>"""


@pytest.fixture
def svg_files(tmp_path):
    """Create various SVG test files and return their paths."""
    files = {}

    # Create different SVG files
    files["copper"] = tmp_path / "copper.svg"
    files["copper"].write_text(SVG_WITH_COPPER_COLOR)

    files["copper_stroke"] = tmp_path / "copper_stroke.svg"
    files["copper_stroke"].write_text(SVG_WITH_COPPER_FILL_AND_STROKE)

    files["copper_with_width"] = tmp_path / "copper_with_width.svg"
    files["copper_with_width"].write_text(SVG_WITH_COPPER_AND_STROKE_WIDTH)

    files["no_copper"] = tmp_path / "no_copper.svg"
    files["no_copper"].write_text(SVG_WITHOUT_COPPER_COLOR)

    files["minimal"] = tmp_path / "minimal.svg"
    files["minimal"].write_text(SVG_MINIMAL)

    files["hex_colors"] = tmp_path / "hex_colors.svg"
    files["hex_colors"].write_text(SVG_WITH_HEX_COLORS)

    files["rgb_color"] = tmp_path / "rgb_color.svg"
    files["rgb_color"].write_text(SVG_WITH_RGB_COLOR)

    files["mixed_red"] = tmp_path / "mixed_red.svg"
    files["mixed_red"].write_text(SVG_WITH_MIXED_RED_COLORS)

    return files


@pytest.fixture
def output_file(tmp_path):
    """Create an output file path."""
    return tmp_path / "output.svg"


class TestParseColor:
    """Test parse_color function with various input formats."""

    @pytest.mark.parametrize(
        "input_color,expected",
        [
            # Hex formats
            ("#FF0000", "#FF0000"),
            ("#ff0000", "#FF0000"),
            ("#AbCdEf", "#ABCDEF"),
            ("#123456", "#123456"),
            ("#000000", "#000000"),
            ("#FFFFFF", "#FFFFFF"),
            # Hex with alpha (should truncate alpha)
            ("#FF0000FF", "#FF0000"),
            ("#12345678", "#123456"),
            # RGB formats
            ("rgb(255, 0, 0)", "#FF0000"),
            ("rgb(0, 255, 0)", "#00FF00"),
            ("rgb(0, 0, 255)", "#0000FF"),
            ("rgb(128, 128, 128)", "#808080"),
            ("rgb(0, 0, 0)", "#000000"),
            ("rgb(255, 255, 255)", "#FFFFFF"),
            # RGB with spaces
            ("rgb( 255 , 0 , 0 )", "#FF0000"),
            ("rgb(255,0,0)", "#FF0000"),
            # RGBA (should ignore alpha)
            ("rgba(255, 0, 0, 1.0)", "#FF0000"),
            ("rgba(255, 0, 0, 0.5)", "#FF0000"),
            ("rgba(128, 64, 32, 0.75)", "#804020"),
            # Named colors
            ("red", "#FF0000"),
            ("green", "#008000"),
            ("blue", "#0000FF"),
            ("white", "#FFFFFF"),
            ("black", "#000000"),
            ("RED", "#FF0000"),  # Case insensitive
            ("Green", "#008000"),
            ("BLUE", "#0000FF"),
            ("cyan", "#00FFFF"),
            ("magenta", "#FF00FF"),
            ("yellow", "#FFFF00"),
            ("orange", "#FFA500"),
            ("purple", "#800080"),
            ("lime", "#00FF00"),
            ("navy", "#000080"),
        ],
    )
    def test_valid_colors(self, input_color, expected):
        """Test parsing of valid color formats."""
        result = parse_color(input_color)
        assert result == expected
        assert isinstance(result, str)
        assert len(result) == 7
        assert result.startswith("#")

    @pytest.mark.parametrize(
        "invalid_color",
        [
            # Invalid hex
            "#GG0000",
            "#12345",  # Too short
            "#1234567",  # Too long (but not 8)
            "FF0000",  # Missing #
            "#",
            "#GGGGGG",
            # Invalid RGB values
            "rgb(256, 0, 0)",  # > 255
            "rgb(-1, 0, 0)",  # < 0
            "rgb(255, 256, 0)",
            "rgb(255, 0, -1)",
            "rgb(300, 300, 300)",
            # Invalid RGB format
            "rgb(255, 0)",  # Missing value
            "rgb(255, 0, 0, 0)",  # Too many values
            "rgb(255.5, 0, 0)",  # Float values
            "rgb(a, b, c)",  # Non-numeric
            # Invalid named colors
            "redish",
            "not_a_color",
            "rgb",
            "hex",
            # Invalid types and empty
            "",
            "   ",
            None,
            123,
            [],
            {},
        ],
    )
    def test_invalid_colors(self, invalid_color):
        """Test that invalid colors raise ColorError."""
        with pytest.raises(ColorError):
            parse_color(invalid_color)

    def test_whitespace_handling(self):
        """Test that whitespace is properly handled."""
        assert parse_color("  #FF0000  ") == "#FF0000"
        assert parse_color("\t#00FF00\n") == "#00FF00"
        assert parse_color("  red  ") == "#FF0000"


class TestValidateHexColor:
    """Test validate_hex_color function."""

    @pytest.mark.parametrize(
        "valid_hex",
        [
            "#FF0000",
            "#00FF00",
            "#0000FF",
            "#123456",
            "#ABCDEF",
            "#abcdef",
            "#000000",
            "#FFFFFF",
            "#A1B2C3",
        ],
    )
    def test_valid_hex_colors(self, valid_hex):
        """Test validation of valid hex colors."""
        assert validate_hex_color(valid_hex) is True

    @pytest.mark.parametrize(
        "invalid_hex",
        [
            "#GG0000",
            "#12345",  # Too short
            "#1234567",  # Too long
            "FF0000",  # Missing #
            "#",
            "#GGGGGG",
            "",
            "red",
            "rgb(255,0,0)",
            None,
            123,
        ],
    )
    def test_invalid_hex_colors(self, invalid_hex):
        """Test validation of invalid hex colors."""
        assert validate_hex_color(invalid_hex) is False


class TestLoadColorConfig:
    """Test load_color_config function with various JSON formats."""

    def test_kicad_project_format(self, tmp_path):
        """Test loading from KiCad project file format."""
        config_file = tmp_path / "test.kicad_pro"
        config_data = {
            "net_settings": {
                "net_colors": {
                    "GND": "#FF0000",
                    "VCC": "blue",
                    "SIGNAL*": "rgb(0, 255, 0)",
                }
            }
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        result = load_color_config(config_file)

        assert len(result) == 3
        assert result["GND"] == "#FF0000"
        assert result["VCC"] == "#0000FF"
        assert result["SIGNAL*"] == "#00FF00"

    def test_custom_format(self, tmp_path):
        """Test loading from custom format with top-level net_colors."""
        config_file = tmp_path / "test.json"
        config_data = {
            "net_colors": {
                "PWR": "#FF0000",
                "CLK": "green",
                "DATA[*]": "#0000FF",
            }
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        result = load_color_config(config_file)

        assert len(result) == 3
        assert result["PWR"] == "#FF0000"
        assert result["CLK"] == "#008000"
        assert result["DATA[*]"] == "#0000FF"

    def test_legacy_format(self, tmp_path):
        """Test loading from legacy format (direct mapping)."""
        config_file = tmp_path / "test.json"
        config_data = {
            "NET1": "#123456",
            "NET2": "red",
            "NET3": "rgb(128, 64, 32)",
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        result = load_color_config(config_file)

        assert len(result) == 3
        assert result["NET1"] == "#123456"
        assert result["NET2"] == "#FF0000"
        assert result["NET3"] == "#804020"

    def test_empty_config(self, tmp_path):
        """Test loading empty configuration."""
        config_file = tmp_path / "empty.json"
        with open(config_file, "w") as f:
            json.dump({}, f)

        result = load_color_config(config_file)
        assert result == {}

    def test_none_net_colors(self, tmp_path):
        """Test handling of None net_colors."""
        config_file = tmp_path / "test.json"
        config_data = {"net_settings": {"net_colors": None}}
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        result = load_color_config(config_file)
        assert result == {}

    def test_invalid_colors_skipped(self, tmp_path):
        """Test that invalid colors are skipped with warnings."""
        config_file = tmp_path / "test.json"
        config_data = {
            "net_colors": {
                "VALID": "#FF0000",
                "INVALID1": "not_a_color",
                "INVALID2": "",
                "INVALID3": None,
                "VALID2": "blue",
            }
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        result = load_color_config(config_file)

        # Only valid colors should be included
        assert len(result) == 2
        assert result["VALID"] == "#FF0000"
        assert result["VALID2"] == "#0000FF"
        assert "INVALID1" not in result
        assert "INVALID2" not in result
        assert "INVALID3" not in result

    def test_file_not_found(self, tmp_path):
        """Test error handling for non-existent file."""
        config_file = tmp_path / "nonexistent.json"

        with pytest.raises(ColorError, match="Failed to load color configuration"):
            load_color_config(config_file)

    def test_invalid_json(self, tmp_path):
        """Test error handling for invalid JSON."""
        config_file = tmp_path / "invalid.json"
        with open(config_file, "w") as f:
            f.write("{ invalid json }")

        with pytest.raises(ColorError, match="Failed to load color configuration"):
            load_color_config(config_file)


class TestResolveNetColor:
    """Test resolve_net_color function with exact and wildcard matching."""

    def test_exact_match(self):
        """Test exact net name matching."""
        config = {"GND": "#FF0000", "VCC": "#00FF00", "CLK": "#0000FF"}

        assert resolve_net_color("GND", config) == "#FF0000"
        assert resolve_net_color("VCC", config) == "#00FF00"
        assert resolve_net_color("CLK", config) == "#0000FF"

    def test_no_match(self):
        """Test when no match is found."""
        config = {"GND": "#FF0000", "VCC": "#00FF00"}

        assert resolve_net_color("UNKNOWN", config) is None
        assert resolve_net_color("", config) is None

    def test_empty_config(self):
        """Test with empty configuration."""
        assert resolve_net_color("ANY_NET", {}) is None

    @pytest.mark.parametrize(
        "pattern,net_name,should_match",
        [
            # Wildcard patterns
            ("DATA*", "DATA1", True),
            ("DATA*", "DATA_BUS", True),
            ("DATA*", "DATA", True),
            ("DATA*", "CLK", False),
            ("*_EN", "PWR_EN", True),
            ("*_EN", "CLK_EN", True),
            ("*_EN", "ENABLE", False),
            # Question mark patterns
            ("CLK?", "CLK1", True),
            ("CLK?", "CLK2", True),
            ("CLK?", "CLK", False),
            ("CLK?", "CLK12", False),
            # Bracket patterns (fnmatch doesn't support [*] as intended)
            ("DATA[0-9]", "DATA0", True),
            ("DATA[0-9]", "DATA5", True),
            ("DATA[0-9]", "DATAA", False),
            # Complex patterns
            ("NET_*_CLK", "NET_CPU_CLK", True),
            ("NET_*_CLK", "NET_USB_CLK", True),
            ("NET_*_CLK", "NET_CLK", False),
        ],
    )
    def test_wildcard_matching(self, pattern, net_name, should_match):
        """Test wildcard pattern matching."""
        config = {pattern: "#FF0000", "OTHER": "#00FF00"}

        result = resolve_net_color(net_name, config)
        if should_match:
            assert result == "#FF0000"
        else:
            assert result is None

    def test_pattern_priority(self):
        """Test that longer/more specific patterns take priority."""
        config = {
            "DATA*": "#FF0000",
            "DATA_BUS*": "#00FF00",
            "DATA_BUS_CLK": "#0000FF",
        }

        # Most specific should win
        assert resolve_net_color("DATA_BUS_CLK", config) == "#0000FF"
        # More specific pattern should win over general
        assert resolve_net_color("DATA_BUS_EN", config) == "#00FF00"
        # General pattern
        assert resolve_net_color("DATA_OTHER", config) == "#FF0000"


class TestGroupNetsByColor:
    """Test group_nets_by_color function."""

    def test_basic_grouping(self):
        """Test basic net grouping by color."""
        net_names = ["GND", "VCC", "CLK", "DATA"]
        net_colors = {"GND": "#FF0000", "VCC": "#FF0000", "CLK": "#00FF00"}

        color_groups, default_nets = group_nets_by_color(net_names, net_colors)

        assert len(color_groups) == 2
        assert set(color_groups["#FF0000"]) == {"GND", "VCC"}
        assert color_groups["#00FF00"] == ["CLK"]
        assert default_nets == ["DATA"]

    def test_empty_nets(self):
        """Test with empty net list."""
        color_groups, default_nets = group_nets_by_color([], {})

        assert color_groups == {}
        assert default_nets == []

    def test_no_colors_defined(self):
        """Test when no colors are defined."""
        net_names = ["NET1", "NET2", "NET3"]

        color_groups, default_nets = group_nets_by_color(net_names, {})

        assert color_groups == {}
        assert set(default_nets) == {"NET1", "NET2", "NET3"}

    def test_all_nets_have_colors(self):
        """Test when all nets have defined colors."""
        net_names = ["A", "B", "C"]
        net_colors = {"A": "#FF0000", "B": "#00FF00", "C": "#FF0000"}

        color_groups, default_nets = group_nets_by_color(net_names, net_colors)

        assert len(color_groups) == 2
        assert set(color_groups["#FF0000"]) == {"A", "C"}
        assert color_groups["#00FF00"] == ["B"]
        assert default_nets == []


class TestNetNameToCssClass:
    """Test net_name_to_css_class function."""

    @pytest.mark.parametrize(
        "net_name,expected",
        [
            # Basic names
            ("GND", "net-gnd"),
            ("VCC", "net-vcc"),
            ("CLK", "net-clk"),
            # Names with special characters
            ("DATA/BUS", "net-data-bus"),
            ("PWR\\EN", "net-pwr-en"),
            ("NET(1)", "net-net-1"),
            ("SIG_A", "net-sig-a"),
            ("CLK.OUT", "net-clk-out"),
            ("USB{P}", "net-usb-p"),
            ("USB:DP", "net-usb-dp"),
            ("NET<0>", "net-net0"),
            # Multiple consecutive special chars
            ("A//B", "net-a-b"),
            ("X__Y", "net-x-y"),
            ("M..N", "net-m-n"),
            # Leading/trailing special chars
            ("/NET/", "net-net"),
            ("_CLK_", "net-clk"),
            ("(SIG)", "net-sig"),
            # Names starting with numbers
            ("1_NET", "net-net-1-net"),
            ("2CLK", "net-net-2clk"),
            # Empty and edge cases
            ("", "net-unknown-net"),
            ("123", "net-net-123"),
            ("___", "net-unknown-net"),
        ],
    )
    def test_css_class_generation(self, net_name, expected):
        """Test CSS class name generation."""
        result = net_name_to_css_class(net_name)
        assert result == expected
        assert result.startswith("net-")


class TestFindCopperColorInSvg:
    """Test find_copper_color_in_svg function."""

    def test_find_fill_attribute(self, tmp_path):
        """Test finding color in fill attribute."""
        svg_content = """<?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg">
            <rect fill="#FF0000" width="10" height="10"/>
            <circle fill="#00FF00" r="5"/>
        </svg>"""

        svg_file = tmp_path / "test.svg"
        with open(svg_file, "w") as f:
            f.write(svg_content)

        result = find_copper_color_in_svg(svg_file)
        # Should return first non-blacklisted color
        assert result in ["#FF0000", "#00FF00"]

    def test_find_fill_in_style(self, tmp_path):
        """Test finding color in style attribute."""
        svg_content = """<?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg">
            <rect style="fill:#123456; stroke:none" width="10" height="10"/>
        </svg>"""

        svg_file = tmp_path / "test.svg"
        with open(svg_file, "w") as f:
            f.write(svg_content)

        result = find_copper_color_in_svg(svg_file)
        assert result == "#123456"

    def test_ignore_blacklisted_colors(self, tmp_path):
        """Test that blacklisted colors are ignored."""
        svg_content = """<?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg">
            <rect fill="#000000" width="10" height="10"/>
            <rect fill="#FFFFFF" width="10" height="10"/>
            <rect fill="#FF0000" width="10" height="10"/>
        </svg>"""

        svg_file = tmp_path / "test.svg"
        with open(svg_file, "w") as f:
            f.write(svg_content)

        result = find_copper_color_in_svg(svg_file)
        # Should skip black and white, return red
        assert result == "#FF0000"

    def test_no_color_found(self, tmp_path):
        """Test when no copper color is found."""
        svg_content = """<?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg">
            <rect fill="#000000" width="10" height="10"/>
            <rect fill="#FFFFFF" width="10" height="10"/>
        </svg>"""

        svg_file = tmp_path / "test.svg"
        with open(svg_file, "w") as f:
            f.write(svg_content)

        result = find_copper_color_in_svg(svg_file)
        assert result is None

    def test_invalid_svg_file(self, tmp_path):
        """Test handling of invalid SVG file."""
        svg_file = tmp_path / "invalid.svg"
        with open(svg_file, "w") as f:
            f.write("not valid xml")

        result = find_copper_color_in_svg(svg_file)
        assert result is None

    def test_nonexistent_file(self, tmp_path):
        """Test handling of non-existent file."""
        svg_file = tmp_path / "nonexistent.svg"

        result = find_copper_color_in_svg(svg_file)
        assert result is None


class TestChangeSvgColor:
    """Test change_svg_color function."""

    def test_color_replacement(self, svg_files, output_file):
        """Test basic color replacement."""
        change_svg_color(svg_files["mixed_red"], "#FF0000", "#00FF00", output_file)

        result_content = output_file.read_text()

        # All instances should be replaced
        assert "#FF0000" not in result_content
        assert "#ff0000" not in result_content
        assert "#00FF00" in result_content or "#00ff00" in result_content

    def test_rgb_replacement(self, svg_files, output_file):
        """Test RGB format replacement."""
        change_svg_color(svg_files["rgb_color"], "#FF0000", "#00FF00", output_file)

        result_content = output_file.read_text()

        # RGB should be replaced
        assert "rgb(255,0,0)" not in result_content
        assert "rgb(0,255,0)" in result_content

    def test_invalid_color_format(self, svg_files, output_file):
        """Test error handling for invalid color formats."""
        # Invalid old color
        with pytest.raises(ColorError, match="Invalid old color format"):
            change_svg_color(
                svg_files["minimal"], "not_a_color", "#00FF00", output_file
            )

        # Invalid new color
        with pytest.raises(ColorError, match="Invalid new color format"):
            change_svg_color(
                svg_files["minimal"], "#FF0000", "not_a_color", output_file
            )

    def test_file_not_found(self, tmp_path):
        """Test error handling for non-existent input file."""
        input_file = tmp_path / "nonexistent.svg"
        output_file = tmp_path / "output.svg"

        with pytest.raises(ColorError, match="Failed to read SVG file"):
            change_svg_color(input_file, "#FF0000", "#00FF00", output_file)

    def test_output_file_write_error(self, svg_files, tmp_path):
        """Test error handling for output file write errors."""
        # Create a directory with the same name as output file to cause write error
        output_dir = tmp_path / "output.svg"
        output_dir.mkdir()

        with pytest.raises(ColorError, match="Failed to write SVG file"):
            change_svg_color(svg_files["minimal"], "#FF0000", "#00FF00", output_dir)


class TestApplyCssClassToSvg:
    """Test apply_css_class_to_svg function."""

    def test_basic_css_class_application(self, svg_files, output_file):
        """Test basic CSS class application to SVG."""
        apply_css_class_to_svg(
            svg_files["copper_stroke"], "VCC", "#FF0000", output_file
        )

        result = output_file.read_text()

        # Should have CSS style section
        assert ".net-vcc" in result
        assert "fill: #FF0000;" in result
        assert "stroke: #FF0000;" in result

        # Should have class attribute
        assert 'class="net-vcc"' in result

        # Should not have original color in style
        assert "fill:#B28C00" not in result

    def test_no_copper_color_detected(self, svg_files, output_file):
        """Test handling when no copper color is detected."""
        apply_css_class_to_svg(svg_files["no_copper"], "VCC", "#FF0000", output_file)

        # Should copy file unchanged
        result = output_file.read_text()
        expected = svg_files["no_copper"].read_text()

        assert result == expected

    def test_invalid_color_format(self, svg_files, output_file):
        """Test error handling for invalid color format."""
        with pytest.raises(ColorError, match="Invalid color"):
            apply_css_class_to_svg(
                svg_files["minimal"], "VCC", "invalid_color", output_file
            )

    def test_css_class_name_generation(self, svg_files, output_file):
        """Test CSS class name generation from various net names."""
        # Test various net names
        test_cases = [
            ("VCC", "net-vcc"),
            ("GND", "net-gnd"),
            ("DATA_BUS", "net-data-bus"),
            ("CLK/RST", "net-clk-rst"),
            ("3V3", "net-net-3v3"),  # 3V3 starts with digit, gets "net-" prefix
        ]

        for net_name, expected_class in test_cases:
            apply_css_class_to_svg(
                svg_files["copper"], net_name, "#FF0000", output_file
            )

            result = output_file.read_text()

            assert f".{expected_class}" in result
            assert f'class="{expected_class}"' in result

    def test_stroke_and_fill_replacement(self, svg_files, output_file):
        """Test replacement of both stroke and fill colors."""
        apply_css_class_to_svg(
            svg_files["copper_with_width"], "VCC", "#FF0000", output_file
        )

        result = output_file.read_text()

        # Should remove both fill and stroke
        assert "fill:#B28C00" not in result
        assert "stroke:#B28C00" not in result

        # Should preserve other style properties
        assert "stroke-width:0.1" in result

        # Should have class
        assert 'class="net-vcc"' in result

    def test_file_write_error(self, svg_files, tmp_path):
        """Test error handling for file write errors."""
        # Create a directory with output file name to cause write error
        output_dir = tmp_path / "output_dir.svg"
        output_dir.mkdir()

        with pytest.raises(ColorError, match="Failed to write SVG file"):
            apply_css_class_to_svg(svg_files["copper"], "VCC", "#FF0000", output_dir)


class TestApplyColorToSvg:
    """Test apply_color_to_svg function."""

    def test_basic_color_application(self, svg_files, output_file):
        """Test basic color application to SVG."""
        apply_color_to_svg(svg_files["copper"], "#FF0000", output_file)

        result = output_file.read_text()

        # Should have new color
        assert "#FF0000" in result
        # Should not have old color
        assert "#B28C00" not in result

    def test_no_copper_color_detected(self, svg_files, output_file):
        """Test handling when no copper color is detected."""
        apply_color_to_svg(svg_files["no_copper"], "#FF0000", output_file)

        # Should copy file unchanged
        result = output_file.read_text()
        expected = svg_files["no_copper"].read_text()

        assert result == expected

    def test_invalid_color_format(self, svg_files, output_file):
        """Test error handling for invalid color format."""
        with pytest.raises(ColorError, match="Invalid net color"):
            apply_color_to_svg(svg_files["minimal"], "invalid_color", output_file)

    def test_various_color_formats(self, svg_files, output_file):
        """Test applying various color formats."""
        # Test different color formats
        test_colors = [
            "#FF0000",  # hex
            "red",  # named
            "rgb(255, 0, 0)",  # rgb
        ]

        for color in test_colors:
            apply_color_to_svg(svg_files["copper"], color, output_file)

            result = output_file.read_text()

            # All should result in #FF0000
            assert "#FF0000" in result
            assert "#B28C00" not in result
