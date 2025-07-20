# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the layers module."""

import pytest

from kicad_svg_extras.layers import (
    LayerInfo,
    LayerType,
    get_copper_layers,
    get_default_copper_layers,
    get_layer_info,
    get_non_copper_layers,
    is_copper_layer,
    parse_layer_list,
    sort_layers_by_stackup,
    suggest_layer_presets,
    validate_layers,
)

pytestmark = pytest.mark.unit


class TestLayerInfo:
    """Test LayerInfo dataclass functionality."""

    def test_layer_info_creation(self):
        """Test creating a LayerInfo object."""
        layer = LayerInfo("F.Cu", LayerType.COPPER, True, 100, "front")
        assert layer.name == "F.Cu"
        assert layer.layer_type == LayerType.COPPER
        assert layer.is_copper is True
        assert layer.order_priority == 100
        assert layer.side == "front"

    def test_layer_info_defaults(self):
        """Test LayerInfo with default side parameter."""
        layer = LayerInfo("Edge.Cuts", LayerType.EDGE_CUTS, False, 1)
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
        assert unknown.order_priority == 9999

    def test_internal_layer_priorities(self):
        """Test that internal layers have correct priority ordering."""
        in1 = get_layer_info("In1.Cu")
        in2 = get_layer_info("In2.Cu")
        in15 = get_layer_info("In15.Cu")

        # Internal layers should be ordered sequentially
        assert in1.order_priority < in2.order_priority
        assert in2.order_priority < in15.order_priority

        # Should be between F.Cu and B.Cu
        f_cu = get_layer_info("F.Cu")
        b_cu = get_layer_info("B.Cu")
        assert f_cu.order_priority < in1.order_priority < b_cu.order_priority


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


class TestSortLayersByStackup:
    """Test sort_layers_by_stackup function."""

    def test_sort_copper_layers_normal(self):
        """Test sorting copper layers in normal order."""
        layers = ["B.Cu", "In2.Cu", "F.Cu", "In1.Cu"]
        sorted_layers = sort_layers_by_stackup(layers)
        assert sorted_layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

    def test_sort_copper_layers_reverse(self):
        """Test sorting copper layers in reverse order."""
        layers = ["B.Cu", "In2.Cu", "F.Cu", "In1.Cu"]
        sorted_layers = sort_layers_by_stackup(layers, reverse=True)
        assert sorted_layers == ["B.Cu", "In2.Cu", "In1.Cu", "F.Cu"]

    def test_sort_mixed_layers(self):
        """Test sorting mixed copper and non-copper layers."""
        layers = ["B.Cu", "F.SilkS", "F.Cu", "Edge.Cuts", "B.SilkS"]
        sorted_layers = sort_layers_by_stackup(layers)
        # Edge.Cuts has priority 1, F.SilkS has 50, F.Cu has 100,
        # B.Cu has 900, B.SilkS has 950
        assert sorted_layers == ["Edge.Cuts", "F.SilkS", "F.Cu", "B.Cu", "B.SilkS"]

    def test_sort_with_user_layers(self):
        """Test sorting with user-defined layers."""
        layers = ["User.1", "F.Cu", "User.2"]
        sorted_layers = sort_layers_by_stackup(layers)
        # F.Cu priority 100, User.1 priority 1021, User.2 priority 1022
        assert sorted_layers == ["F.Cu", "User.1", "User.2"]

    def test_sort_empty_list(self):
        """Test sorting empty list."""
        sorted_layers = sort_layers_by_stackup([])
        assert sorted_layers == []

    def test_sort_single_layer(self):
        """Test sorting single layer."""
        sorted_layers = sort_layers_by_stackup(["F.Cu"])
        assert sorted_layers == ["F.Cu"]


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


class TestGetDefaultCopperLayers:
    """Test get_default_copper_layers function."""

    def test_2_layer_board(self):
        """Test default layers for 2-layer board."""
        layers = get_default_copper_layers(2)
        assert layers == ["F.Cu", "B.Cu"]

    def test_4_layer_board(self):
        """Test default layers for 4-layer board."""
        layers = get_default_copper_layers(4)
        assert layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

    def test_6_layer_board(self):
        """Test default layers for 6-layer board."""
        layers = get_default_copper_layers(6)
        assert layers == ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]

    def test_8_layer_board(self):
        """Test default layers for 8-layer board."""
        layers = get_default_copper_layers(8)
        expected = [
            "F.Cu",
            "In1.Cu",
            "In2.Cu",
            "In3.Cu",
            "In4.Cu",
            "In5.Cu",
            "In6.Cu",
            "B.Cu",
        ]
        assert layers == expected

    def test_invalid_layer_count_odd(self):
        """Test invalid odd layer count."""
        with pytest.raises(
            ValueError, match="Number of copper layers must be even and >= 2"
        ):
            get_default_copper_layers(3)

    def test_invalid_layer_count_one(self):
        """Test invalid single layer count."""
        with pytest.raises(
            ValueError, match="Number of copper layers must be even and >= 2"
        ):
            get_default_copper_layers(1)

    def test_invalid_layer_count_zero(self):
        """Test invalid zero layer count."""
        with pytest.raises(
            ValueError, match="Number of copper layers must be even and >= 2"
        ):
            get_default_copper_layers(0)

    def test_invalid_layer_count_negative(self):
        """Test invalid negative layer count."""
        with pytest.raises(
            ValueError, match="Number of copper layers must be even and >= 2"
        ):
            get_default_copper_layers(-2)


class TestSuggestLayerPresets:
    """Test suggest_layer_presets function."""

    def test_preset_types(self):
        """Test that presets return expected types."""
        presets = suggest_layer_presets()
        assert isinstance(presets, dict)
        for preset_name, layers in presets.items():
            assert isinstance(preset_name, str)
            assert isinstance(layers, list)
            for layer in layers:
                assert isinstance(layer, str)

    def test_preset_names(self):
        """Test expected preset names exist."""
        presets = suggest_layer_presets()
        expected_presets = {
            "copper_2layer",
            "copper_4layer",
            "front_assembly",
            "back_assembly",
            "all_copper",
            "documentation",
        }
        assert set(presets.keys()) == expected_presets

    def test_preset_contents(self):
        """Test preset contents are sensible."""
        presets = suggest_layer_presets()

        # Test 2-layer copper preset
        assert presets["copper_2layer"] == ["F.Cu", "B.Cu"]

        # Test 4-layer copper preset
        assert presets["copper_4layer"] == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

        # Test front assembly includes F.Cu, F.SilkS, and Edge.Cuts
        front_assembly = presets["front_assembly"]
        assert "F.Cu" in front_assembly
        assert "F.SilkS" in front_assembly
        assert "Edge.Cuts" in front_assembly

        # Test back assembly includes B.Cu, B.SilkS, and Edge.Cuts
        back_assembly = presets["back_assembly"]
        assert "B.Cu" in back_assembly
        assert "B.SilkS" in back_assembly
        assert "Edge.Cuts" in back_assembly

        # Test documentation preset includes silkscreen and edge cuts
        documentation = presets["documentation"]
        assert "F.SilkS" in documentation
        assert "B.SilkS" in documentation
        assert "Edge.Cuts" in documentation

    def test_preset_layer_validity(self):
        """Test that all preset layers are valid."""
        presets = suggest_layer_presets()
        for preset_name, layers in presets.items():
            invalid_layers = validate_layers(layers)
            assert (
                invalid_layers == []
            ), f"Preset {preset_name} contains invalid layers: {invalid_layers}"


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

        # Sort by stackup order
        sorted_layers = sort_layers_by_stackup(layers)
        # Edge.Cuts (1), F.SilkS (50), F.Cu (100), In1.Cu (200), In2.Cu (220),
        # B.Cu (900), B.SilkS (950)
        expected_order = [
            "Edge.Cuts",
            "F.SilkS",
            "F.Cu",
            "In1.Cu",
            "In2.Cu",
            "B.Cu",
            "B.SilkS",
        ]
        assert sorted_layers == expected_order

        # Test reverse order
        sorted_layers_reverse = sort_layers_by_stackup(layers, reverse=True)
        assert sorted_layers_reverse == list(reversed(expected_order))

    def test_preset_workflow(self):
        """Test workflow using presets."""
        presets = suggest_layer_presets()

        # Test 4-layer preset workflow
        layers = presets["copper_4layer"]
        invalid = validate_layers(layers)
        assert invalid == []

        copper_layers = get_copper_layers(layers)
        assert len(copper_layers) == 4
        assert all(is_copper_layer(layer) for layer in copper_layers)

        # Test documentation preset workflow
        doc_layers = presets["documentation"]
        invalid = validate_layers(doc_layers)
        assert invalid == []

        sorted_doc = sort_layers_by_stackup(doc_layers)
        # Should have Edge.Cuts first (priority 1), then other layers by priority
        assert sorted_doc[0] == "Edge.Cuts"

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
