# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the layers module."""

import pytest

from kicad_svg_extras.layers import (
    LayerInfo,
    LayerType,
    get_copper_layers,
    get_layer_info,
    get_non_copper_layers,
    is_copper_layer,
    parse_layer_list,
    validate_layers,
)

pytestmark = pytest.mark.unit


class TestLayerInfo:
    """Test LayerInfo dataclass functionality."""

    def test_layer_info_creation(self):
        """Test creating a LayerInfo object."""
        layer = LayerInfo("F.Cu", LayerType.COPPER, True, "front")
        assert layer.name == "F.Cu"
        assert layer.layer_type == LayerType.COPPER
        assert layer.is_copper is True
        assert layer.side == "front"

    def test_layer_info_defaults(self):
        """Test LayerInfo with default side parameter."""
        layer = LayerInfo("Edge.Cuts", LayerType.EDGE_CUTS, False)
        assert layer.side == ""


class TestGetLayerInfo:
    """Test get_layer_info function."""

    def test_get_layer_info_known_layers(self):
        """Test getting info for known layers."""
        # Test copper layers
        f_cu = get_layer_info("F.Cu")
        assert f_cu.name == "F.Cu"
        assert f_cu.layer_type == LayerType.COPPER
        assert f_cu.is_copper is True
        assert f_cu.side == "front"

        b_cu = get_layer_info("B.Cu")
        assert b_cu.name == "B.Cu"
        assert b_cu.layer_type == LayerType.COPPER
        assert b_cu.is_copper is True
        assert b_cu.side == "back"

        # Test internal copper layers
        in1_cu = get_layer_info("In1.Cu")
        assert in1_cu.name == "In1.Cu"
        assert in1_cu.layer_type == LayerType.COPPER
        assert in1_cu.is_copper is True
        assert in1_cu.side == "internal"

        in30_cu = get_layer_info("In30.Cu")
        assert in30_cu.name == "In30.Cu"
        assert in30_cu.layer_type == LayerType.COPPER
        assert in30_cu.is_copper is True

        # Test non-copper layers
        edge_cuts = get_layer_info("Edge.Cuts")
        assert edge_cuts.name == "Edge.Cuts"
        assert edge_cuts.layer_type == LayerType.EDGE_CUTS
        assert edge_cuts.is_copper is False

        f_silks = get_layer_info("F.SilkS")
        assert f_silks.name == "F.SilkS"
        assert f_silks.layer_type == LayerType.SILKSCREEN
        assert f_silks.is_copper is False
        assert f_silks.side == "front"

    def test_get_layer_info_unknown_layer(self):
        """Test getting info for unknown layer."""
        unknown = get_layer_info("Unknown.Layer")
        assert unknown.name == "Unknown.Layer"
        assert unknown.layer_type == LayerType.UNKNOWN
        assert unknown.is_copper is False


class TestIsCopperLayer:
    """Test is_copper_layer function."""

    def test_copper_layers(self):
        """Test copper layer detection."""
        assert is_copper_layer("F.Cu") is True
        assert is_copper_layer("B.Cu") is True
        assert is_copper_layer("In1.Cu") is True
        assert is_copper_layer("In2.Cu") is True
        assert is_copper_layer("In30.Cu") is True

    def test_non_copper_layers(self):
        """Test non-copper layer detection."""
        assert is_copper_layer("F.SilkS") is False
        assert is_copper_layer("B.SilkS") is False
        assert is_copper_layer("Edge.Cuts") is False
        assert is_copper_layer("F.Mask") is False
        assert is_copper_layer("B.Mask") is False
        assert is_copper_layer("F.Fab") is False
        assert is_copper_layer("User.1") is False

    def test_unknown_layers(self):
        """Test unknown layer detection."""
        assert is_copper_layer("Unknown.Layer") is False


class TestParseLayerList:
    """Test parse_layer_list function."""

    def test_parse_simple_list(self):
        """Test parsing simple layer list."""
        result = parse_layer_list("F.Cu,B.Cu")
        assert result == ["F.Cu", "B.Cu"]

    def test_parse_complex_list(self):
        """Test parsing complex layer list."""
        result = parse_layer_list("F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,Edge.Cuts")
        expected = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.SilkS", "Edge.Cuts"]
        assert result == expected

    def test_parse_with_spaces(self):
        """Test parsing layer list with spaces."""
        result = parse_layer_list("F.Cu, B.Cu , In1.Cu")
        assert result == ["F.Cu", "B.Cu", "In1.Cu"]

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_layer_list("")
        assert result == []

    def test_parse_whitespace_only(self):
        """Test parsing whitespace-only string."""
        result = parse_layer_list("   ")
        assert result == []

    def test_parse_with_empty_elements(self):
        """Test parsing with empty elements."""
        result = parse_layer_list("F.Cu,,B.Cu,")
        assert result == ["F.Cu", "B.Cu"]


class TestValidateLayers:
    """Test validate_layers function."""

    def test_validate_known_layers(self):
        """Test validating known layers."""
        layers = ["F.Cu", "B.Cu", "In1.Cu", "F.SilkS", "Edge.Cuts"]
        invalid = validate_layers(layers)
        assert invalid == []

    def test_validate_unknown_layers(self):
        """Test validating unknown layers."""
        layers = ["F.Cu", "Unknown.Layer", "B.Cu", "Invalid.Layer"]
        invalid = validate_layers(layers)
        assert set(invalid) == {"Unknown.Layer", "Invalid.Layer"}

    def test_validate_mixed_layers(self):
        """Test validating mix of known and unknown layers."""
        layers = ["F.Cu", "B.Cu", "Unknown.Layer"]
        invalid = validate_layers(layers)
        assert invalid == ["Unknown.Layer"]

    def test_validate_empty_list(self):
        """Test validating empty layer list."""
        invalid = validate_layers([])
        assert invalid == []


class TestGetCopperLayers:
    """Test get_copper_layers function."""

    def test_filter_copper_only(self):
        """Test filtering copper layers only."""
        layers = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]
        copper_layers = get_copper_layers(layers)
        assert copper_layers == ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]

    def test_filter_mixed_layers(self):
        """Test filtering copper from mixed layers."""
        layers = ["F.Cu", "F.SilkS", "B.Cu", "Edge.Cuts", "In1.Cu"]
        copper_layers = get_copper_layers(layers)
        assert copper_layers == ["F.Cu", "B.Cu", "In1.Cu"]

    def test_filter_no_copper(self):
        """Test filtering with no copper layers."""
        layers = ["F.SilkS", "B.SilkS", "Edge.Cuts", "F.Mask"]
        copper_layers = get_copper_layers(layers)
        assert copper_layers == []

    def test_filter_empty_list(self):
        """Test filtering empty list."""
        copper_layers = get_copper_layers([])
        assert copper_layers == []


class TestGetNonCopperLayers:
    """Test get_non_copper_layers function."""

    def test_filter_non_copper_only(self):
        """Test filtering non-copper layers only."""
        layers = ["F.SilkS", "B.SilkS", "Edge.Cuts", "F.Mask"]
        non_copper_layers = get_non_copper_layers(layers)
        assert non_copper_layers == ["F.SilkS", "B.SilkS", "Edge.Cuts", "F.Mask"]

    def test_filter_mixed_layers(self):
        """Test filtering non-copper from mixed layers."""
        layers = ["F.Cu", "F.SilkS", "B.Cu", "Edge.Cuts", "In1.Cu"]
        non_copper_layers = get_non_copper_layers(layers)
        assert non_copper_layers == ["F.SilkS", "Edge.Cuts"]

    def test_filter_no_non_copper(self):
        """Test filtering with no non-copper layers."""
        layers = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]
        non_copper_layers = get_non_copper_layers(layers)
        assert non_copper_layers == []

    def test_filter_empty_list(self):
        """Test filtering empty list."""
        non_copper_layers = get_non_copper_layers([])
        assert non_copper_layers == []


class TestLayerTypeEnum:
    """Test LayerType enum."""

    def test_layer_types_exist(self):
        """Test that expected layer types exist."""
        expected_types = {
            "COPPER",
            "SILKSCREEN",
            "SOLDER_MASK",
            "SOLDER_PASTE",
            "FABRICATION",
            "COURTYARD",
            "ADHESIVE",
            "EDGE_CUTS",
            "DOCUMENTATION",
            "USER",
            "UNKNOWN",
        }
        actual_types = {lt.name for lt in LayerType}
        assert actual_types == expected_types

    def test_layer_type_values(self):
        """Test layer type string values."""
        assert LayerType.COPPER.value == "copper"
        assert LayerType.SILKSCREEN.value == "silkscreen"
        assert LayerType.EDGE_CUTS.value == "edge_cuts"
        assert LayerType.UNKNOWN.value == "unknown"


class TestLayerIntegration:
    """Integration tests for layer functions working together."""

    def test_full_workflow_4layer(self):
        """Test complete workflow for 4-layer board."""
        # Parse layer specification
        layer_spec = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts"
        layers = parse_layer_list(layer_spec)

        # Validate layers
        invalid = validate_layers(layers)
        assert invalid == []

        # Separate copper and non-copper
        copper_layers = get_copper_layers(layers)
        non_copper_layers = get_non_copper_layers(layers)

        assert copper_layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        assert non_copper_layers == ["F.SilkS", "B.SilkS", "Edge.Cuts"]

    def test_basic_workflow(self):
        """Test basic layer processing workflow."""
        # Test 4-layer workflow
        layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        invalid = validate_layers(layers)
        assert invalid == []

        copper_layers = get_copper_layers(layers)
        assert len(copper_layers) == 4
        assert all(is_copper_layer(layer) for layer in copper_layers)

        # Test documentation layers workflow
        doc_layers = ["F.Cu", "B.Cu", "F.SilkS", "B.SilkS", "Edge.Cuts"]
        invalid = validate_layers(doc_layers)
        assert invalid == []

    def test_error_handling_workflow(self):
        """Test workflow with invalid inputs."""
        # Test with invalid layer spec
        layers = parse_layer_list("F.Cu,Invalid.Layer,B.Cu")
        invalid = validate_layers(layers)
        assert "Invalid.Layer" in invalid

        # Filter out invalid layers and continue
        valid_layers = [layer for layer in layers if layer not in invalid]
        assert valid_layers == ["F.Cu", "B.Cu"]

        # Continue workflow with valid layers
        copper_layers = get_copper_layers(valid_layers)
        assert copper_layers == ["F.Cu", "B.Cu"]
