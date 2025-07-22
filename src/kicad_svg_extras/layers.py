# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Layer management utilities for KiCad PCB processing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LayerType(Enum):
    """Type classification for KiCad layers."""

    COPPER = "copper"
    SILKSCREEN = "silkscreen"
    SOLDER_MASK = "solder_mask"
    SOLDER_PASTE = "solder_paste"
    FABRICATION = "fabrication"
    COURTYARD = "courtyard"
    ADHESIVE = "adhesive"
    EDGE_CUTS = "edge_cuts"
    DOCUMENTATION = "documentation"
    USER = "user"
    UNKNOWN = "unknown"


@dataclass
class LayerInfo:
    """Information about a KiCad layer."""

    name: str
    layer_type: LayerType
    is_copper: bool
    side: str = ""  # "front", "back", or "internal"


# Standard KiCad layer definitions
LAYER_DEFINITIONS = {
    # Copper layers
    "F.Cu": LayerInfo("F.Cu", LayerType.COPPER, True, "front"),
    "B.Cu": LayerInfo("B.Cu", LayerType.COPPER, True, "back"),
    # Silkscreen layers
    "F.SilkS": LayerInfo("F.SilkS", LayerType.SILKSCREEN, False, "front"),
    "B.SilkS": LayerInfo("B.SilkS", LayerType.SILKSCREEN, False, "back"),
    # Solder mask layers
    "F.Mask": LayerInfo("F.Mask", LayerType.SOLDER_MASK, False, "front"),
    "B.Mask": LayerInfo("B.Mask", LayerType.SOLDER_MASK, False, "back"),
    # Solder paste layers
    "F.Paste": LayerInfo("F.Paste", LayerType.SOLDER_PASTE, False, "front"),
    "B.Paste": LayerInfo("B.Paste", LayerType.SOLDER_PASTE, False, "back"),
    # Fabrication layers
    "F.Fab": LayerInfo("F.Fab", LayerType.FABRICATION, False, "front"),
    "B.Fab": LayerInfo("B.Fab", LayerType.FABRICATION, False, "back"),
    # Courtyard layers
    "F.CrtYd": LayerInfo("F.CrtYd", LayerType.COURTYARD, False, "front"),
    "B.CrtYd": LayerInfo("B.CrtYd", LayerType.COURTYARD, False, "back"),
    # Adhesive layers
    "F.Adhes": LayerInfo("F.Adhes", LayerType.ADHESIVE, False, "front"),
    "B.Adhes": LayerInfo("B.Adhes", LayerType.ADHESIVE, False, "back"),
    # Board definition
    "Edge.Cuts": LayerInfo("Edge.Cuts", LayerType.EDGE_CUTS, False, ""),
    # Documentation layers
    "Dwgs.User": LayerInfo("Dwgs.User", LayerType.DOCUMENTATION, False, ""),
    "Cmts.User": LayerInfo("Cmts.User", LayerType.DOCUMENTATION, False, ""),
    "Eco1.User": LayerInfo("Eco1.User", LayerType.DOCUMENTATION, False, ""),
    "Eco2.User": LayerInfo("Eco2.User", LayerType.DOCUMENTATION, False, ""),
    "Margin": LayerInfo("Margin", LayerType.DOCUMENTATION, False, ""),
}

# Generate internal copper layer definitions (In1.Cu through In30.Cu)
for i in range(1, 31):
    layer_name = f"In{i}.Cu"
    # Priority 200-799 for internal layers (between F.Cu and B.Cu)
    LAYER_DEFINITIONS[layer_name] = LayerInfo(
        layer_name, LayerType.COPPER, True, "internal"
    )

# Generate user-defined layers (User.1 through User.9)
for i in range(1, 10):
    layer_name = f"User.{i}"
    LAYER_DEFINITIONS[layer_name] = LayerInfo(layer_name, LayerType.USER, False, "")


def get_layer_info(layer_name: str) -> LayerInfo:
    """Get layer information for a given layer name.

    Args:
        layer_name: KiCad layer name (e.g., "F.Cu", "In1.Cu")

    Returns:
        LayerInfo object with layer details
    """
    return LAYER_DEFINITIONS.get(
        layer_name, LayerInfo(layer_name, LayerType.UNKNOWN, False)
    )


def is_copper_layer(layer_name: str) -> bool:
    """Check if a layer is a copper layer.

    Args:
        layer_name: KiCad layer name

    Returns:
        True if the layer is copper, False otherwise
    """
    return get_layer_info(layer_name).is_copper


def parse_layer_list(layer_spec: str) -> list[str]:
    """Parse a comma-separated layer specification.

    Args:
        layer_spec: Comma-separated layer names (e.g., "F.Cu,B.Cu,In1.Cu")

    Returns:
        List of layer names
    """
    if not layer_spec.strip():
        return []

    return [layer.strip() for layer in layer_spec.split(",") if layer.strip()]


def validate_layers(layer_names: list[str]) -> list[str]:
    """Validate that all layer names are known KiCad layers.

    Args:
        layer_names: List of layer names to validate

    Returns:
        List of invalid layer names (empty if all valid)
    """
    invalid_layers = []
    for layer_name in layer_names:
        if get_layer_info(layer_name).layer_type == LayerType.UNKNOWN:
            invalid_layers.append(layer_name)
    return invalid_layers


def get_copper_layers(layer_names: list[str]) -> list[str]:
    """Filter out only copper layers from a layer list.

    Args:
        layer_names: List of layer names

    Returns:
        List containing only copper layer names
    """
    return [layer for layer in layer_names if is_copper_layer(layer)]


def get_non_copper_layers(layer_names: list[str]) -> list[str]:
    """Filter out only non-copper layers from a layer list.

    Args:
        layer_names: List of layer names

    Returns:
        List containing only non-copper layer names
    """
    return [layer for layer in layer_names if not is_copper_layer(layer)]
