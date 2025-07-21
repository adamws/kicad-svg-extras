# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Layer management utilities for KiCad PCB processing."""

from __future__ import annotations

import logging
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
    order_priority: int  # Lower numbers appear first in stackup
    side: str = ""  # "front", "back", or "internal"


# Standard KiCad layer definitions
LAYER_DEFINITIONS = {
    # Copper layers
    "F.Cu": LayerInfo("F.Cu", LayerType.COPPER, True, 100, "front"),
    "B.Cu": LayerInfo("B.Cu", LayerType.COPPER, True, 900, "back"),
    # Silkscreen layers
    "F.SilkS": LayerInfo("F.SilkS", LayerType.SILKSCREEN, False, 50, "front"),
    "B.SilkS": LayerInfo("B.SilkS", LayerType.SILKSCREEN, False, 950, "back"),
    # Solder mask layers
    "F.Mask": LayerInfo("F.Mask", LayerType.SOLDER_MASK, False, 80, "front"),
    "B.Mask": LayerInfo("B.Mask", LayerType.SOLDER_MASK, False, 920, "back"),
    # Solder paste layers
    "F.Paste": LayerInfo("F.Paste", LayerType.SOLDER_PASTE, False, 70, "front"),
    "B.Paste": LayerInfo("B.Paste", LayerType.SOLDER_PASTE, False, 930, "back"),
    # Fabrication layers
    "F.Fab": LayerInfo("F.Fab", LayerType.FABRICATION, False, 90, "front"),
    "B.Fab": LayerInfo("B.Fab", LayerType.FABRICATION, False, 910, "back"),
    # Courtyard layers
    "F.CrtYd": LayerInfo("F.CrtYd", LayerType.COURTYARD, False, 60, "front"),
    "B.CrtYd": LayerInfo("B.CrtYd", LayerType.COURTYARD, False, 940, "back"),
    # Adhesive layers
    "F.Adhes": LayerInfo("F.Adhes", LayerType.ADHESIVE, False, 85, "front"),
    "B.Adhes": LayerInfo("B.Adhes", LayerType.ADHESIVE, False, 915, "back"),
    # Board definition
    "Edge.Cuts": LayerInfo("Edge.Cuts", LayerType.EDGE_CUTS, False, 1, ""),
    # Documentation layers
    "Dwgs.User": LayerInfo("Dwgs.User", LayerType.DOCUMENTATION, False, 1000, ""),
    "Cmts.User": LayerInfo("Cmts.User", LayerType.DOCUMENTATION, False, 1001, ""),
    "Eco1.User": LayerInfo("Eco1.User", LayerType.DOCUMENTATION, False, 1002, ""),
    "Eco2.User": LayerInfo("Eco2.User", LayerType.DOCUMENTATION, False, 1003, ""),
    "Margin": LayerInfo("Margin", LayerType.DOCUMENTATION, False, 1010, ""),
}

# Generate internal copper layer definitions (In1.Cu through In30.Cu)
for i in range(1, 31):
    layer_name = f"In{i}.Cu"
    # Priority 200-799 for internal layers (between F.Cu and B.Cu)
    priority = 200 + (i - 1) * 20
    LAYER_DEFINITIONS[layer_name] = LayerInfo(
        layer_name, LayerType.COPPER, True, priority, "internal"
    )

# Generate user-defined layers (User.1 through User.9)
for i in range(1, 10):
    layer_name = f"User.{i}"
    LAYER_DEFINITIONS[layer_name] = LayerInfo(
        layer_name, LayerType.USER, False, 1020 + i, ""
    )


def get_layer_info(layer_name: str) -> LayerInfo:
    """Get layer information for a given layer name.

    Args:
        layer_name: KiCad layer name (e.g., "F.Cu", "In1.Cu")

    Returns:
        LayerInfo object with layer details
    """
    return LAYER_DEFINITIONS.get(
        layer_name, LayerInfo(layer_name, LayerType.UNKNOWN, False, 9999)
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


def sort_layers_by_stackup(
    layer_names: list[str], *, reverse: bool = False
) -> list[str]:
    """Sort layers according to physical PCB stackup order.

    Args:
        layer_names: List of layer names to sort
        reverse: If True, sort from back to front (bottom-up view)

    Returns:
        Sorted list of layer names
    """

    def sort_key(layer_name: str) -> int:
        return get_layer_info(layer_name).order_priority

    return sorted(layer_names, key=sort_key, reverse=reverse)


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


def get_default_copper_layers(num_layers: int = 2) -> list[str]:
    """Get default copper layer list for a given number of layers.

    Args:
        num_layers: Number of copper layers (2, 4, 6, 8, etc.)

    Returns:
        List of copper layer names in stackup order

    Raises:
        ValueError: If num_layers is invalid
    """
    min_layers = 2
    if num_layers < min_layers or num_layers % min_layers != 0:
        msg = "Number of copper layers must be even and >= 2"
        raise ValueError(msg)

    if num_layers == min_layers:
        return ["F.Cu", "B.Cu"]

    # Multi-layer board
    layers = ["F.Cu"]

    # Add internal layers
    for i in range(1, num_layers - 1):
        layers.append(f"In{i}.Cu")

    layers.append("B.Cu")
    return layers


def get_enabled_layers_from_pcb(pcb_file_path: str) -> list[str]:
    """Get list of enabled layers from a PCB file.

    Args:
        pcb_file_path: Path to the .kicad_pcb file

    Returns:
        List of enabled layer names

    Raises:
        ImportError: If pcbnew module is not available
        RuntimeError: If PCB file cannot be loaded
    """
    try:
        import pcbnew  # noqa: PLC0415
    except ImportError as e:
        msg = "pcbnew module not available - cannot detect layers from PCB"
        raise ImportError(msg) from e

    try:
        board = pcbnew.LoadBoard(pcb_file_path)
        if not board:
            msg = f"Failed to load PCB file: {pcb_file_path}"
            raise RuntimeError(msg)

        enabled_layers = board.GetEnabledLayers()
        layer_names = []

        # Check all known layers
        for layer_name in LAYER_DEFINITIONS:
            try:
                layer_id = board.GetLayerID(layer_name)
                if enabled_layers.Contains(layer_id):
                    layer_names.append(layer_name)
            except Exception as e:
                # Layer name not recognized by board, skip it
                logger = logging.getLogger(__name__)
                logger.debug(f"Layer '{layer_name}' not recognized by board: {e}")
                continue

        return layer_names

    except Exception as e:
        msg = f"Error reading layers from PCB file: {e}"
        raise RuntimeError(msg) from e


def filter_layers_by_pcb_availability(
    layer_names: list[str], pcb_file_path: str | None = None
) -> list[str]:
    """Filter layer list to only include layers enabled in the PCB.

    Args:
        layer_names: List of layer names to filter
        pcb_file_path: Path to PCB file for layer detection (optional)

    Returns:
        Filtered list of layer names that exist in the PCB

    Note:
        If pcb_file_path is None or layer detection fails, returns original list
    """
    if not pcb_file_path:
        return layer_names

    try:
        enabled_layers = get_enabled_layers_from_pcb(pcb_file_path)
        filtered_layers = [layer for layer in layer_names if layer in enabled_layers]

        # Log information about filtered layers
        logger = logging.getLogger(__name__)
        removed_layers = [layer for layer in layer_names if layer not in enabled_layers]
        if removed_layers:
            logger.info(
                f"Skipping undefined layers: {', '.join(removed_layers)} "
                f"(not enabled in PCB)"
            )
        if filtered_layers:
            logger.debug(f"Processing enabled layers: {', '.join(filtered_layers)}")

        return filtered_layers

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Could not detect PCB layers, processing all requested: {e}")
        return layer_names


def suggest_layer_presets() -> dict[str, list[str]]:
    """Get suggested layer presets for common use cases.

    Returns:
        Dictionary mapping preset names to layer lists
    """
    return {
        "copper_2layer": ["F.Cu", "B.Cu"],
        "copper_4layer": ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
        "front_assembly": ["F.Cu", "F.SilkS", "Edge.Cuts"],
        "back_assembly": ["B.Cu", "B.SilkS", "Edge.Cuts"],
        "all_copper": get_default_copper_layers(4),  # Will be auto-detected later
        "documentation": ["F.Cu", "B.Cu", "F.SilkS", "B.SilkS", "Edge.Cuts"],
    }
