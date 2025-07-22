# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""PCB utilities using pcbnew API.

This module centralizes all pcbnew library interactions including:
- Loading PCB boards
- Extracting net information
- Filtering PCB elements
- Detecting layer availability
- Creating filtered PCB files
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from kicad_svg_extras.layers import LAYER_DEFINITIONS

try:
    import pcbnew
    import wx

    wx.Log.SetLogLevel(wx.LOG_Warning)
except ImportError as err:
    msg = (
        "pcbnew module not available. "
        "This package requires KiCad to be installed with Python bindings. "
        "Please install KiCad and ensure pcbnew is available in your Python "
        "environment."
    )
    raise ImportError(msg) from err

logger = logging.getLogger(__name__)


def load_board(pcb_file: Path):
    """Load a PCB board from file."""
    board = pcbnew.LoadBoard(str(pcb_file))
    if not board:
        msg = f"Failed to load board: {pcb_file}"
        raise RuntimeError(msg)
    return board


def get_net_codes(board) -> dict[str, int]:
    """Get mapping of net name to net code from board."""
    net_codes = {}
    netlist = board.GetNetInfo()
    for net_code in range(netlist.GetNetCount()):
        net_info = netlist.GetNetItem(net_code)
        if net_info:
            net_name = net_info.GetNetname()
            net_codes[net_name] = net_code
    net_codes["<no_net>"] = 0  # Use net code 0 for no net
    return net_codes


def get_net_names(pcb_file: Path) -> list[str]:
    """Get all net names in the PCB."""
    board = load_board(pcb_file)
    net_codes = get_net_codes(board)
    return list(net_codes.keys())


def has_elements_on_side(
    board, net_name: str, side: str, net_codes: dict[str, int]
) -> bool:
    """Check if a net has any tracks, pads, or vias on a given side."""
    if net_name not in net_codes:
        return False

    net_code = net_codes[net_name]
    cu_layer = pcbnew.F_Cu if side == "front" else pcbnew.B_Cu

    for item in board.AllConnectedItems():
        if item.GetNetCode() == net_code and item.IsOnLayer(cu_layer):
            return True

    return False


def has_elements_on_layers(
    board, net_name: str, layers: list[str], net_codes: dict[str, int]
) -> bool:
    """Check if a net has any tracks, pads, or vias on any of the given layers."""
    if net_name not in net_codes:
        return False

    net_code = net_codes[net_name]

    # Convert layer names to KiCad layer IDs
    layer_ids = []
    for layer_name in layers:
        try:
            if layer_name == "F.Cu":
                layer_ids.append(pcbnew.F_Cu)
            elif layer_name == "B.Cu":
                layer_ids.append(pcbnew.B_Cu)
            elif layer_name.startswith("In") and layer_name.endswith(".Cu"):
                # Extract internal layer number (In1.Cu -> 1, In2.Cu -> 2, etc.)
                layer_num_str = layer_name[2:-3]  # Remove "In" and ".Cu"
                layer_num = int(layer_num_str)
                # Internal layers in KiCad use In1_Cu, In2_Cu, etc.
                layer_id = getattr(pcbnew, f"In{layer_num}_Cu", None)
                if layer_id is not None:
                    layer_ids.append(layer_id)
        except (ValueError, AttributeError):
            # Skip invalid layer names
            continue

    # Check if net has elements on any of the specified layers
    for item in board.AllConnectedItems():
        if item.GetNetCode() == net_code:
            for layer_id in layer_ids:
                if item.IsOnLayer(layer_id):
                    return True

    return False


def create_filtered_pcb(
    pcb_file: Path,
    net_names: set[str],
    output_file: Path,
    *,
    skip_zones: bool = False,
) -> None:
    """Create a new PCB file with only the specified nets."""
    logger.debug(f"Creating filtered PCB for nets: {sorted(net_names)}")
    logger.debug(f"  Source: {pcb_file.name}")
    logger.debug(f"  Output: {output_file.name}")

    # Create a copy of the board by copying the original file first
    shutil.copy2(pcb_file, output_file)

    # Load the copied board
    new_board = pcbnew.LoadBoard(str(output_file))

    # Get net codes from original board
    original_board = load_board(pcb_file)
    net_codes = get_net_codes(original_board)

    # Get net codes to keep
    net_codes_to_keep = {
        net_codes[net_name] for net_name in net_names if net_name in net_codes
    }

    # Remove tracks and vias not in specified nets
    tracks_to_remove = []
    for track in new_board.GetTracks():
        if track.GetNetCode() not in net_codes_to_keep:
            tracks_to_remove.append(track)

    for track in tracks_to_remove:
        new_board.RemoveNative(track)

    # Remove footprints that have no pads with specified nets, and remove pads
    # not in specified nets
    footprints_to_remove = []
    for footprint in new_board.GetFootprints():
        # Check if this footprint has any pads with the specified nets
        has_matching_pads = False
        pads_to_remove = []

        for pad in footprint.Pads():
            if pad.GetNetCode() in net_codes_to_keep:
                has_matching_pads = True
            else:
                pads_to_remove.append(pad)

        if has_matching_pads:
            # Remove pads that don't match the specified nets
            for pad in pads_to_remove:
                footprint.RemoveNative(pad)
        else:
            # Remove the entire footprint if it has no matching pads
            footprints_to_remove.append(footprint)

    # Remove footprints with no matching pads
    for footprint in footprints_to_remove:
        new_board.RemoveNative(footprint)

    # Remove zones not matching specified nets
    total_zones = len(list(new_board.Zones()))
    if skip_zones:
        zones_to_remove = list(new_board.Zones())
        logger.debug(f"  Removing all {total_zones} zones (skip_zones=True)")
    else:
        zones_to_remove = []
        zones_kept = []
        for zone in new_board.Zones():
            zone_net = new_board.FindNet(zone.GetNetCode())
            zone_net_name = zone_net.GetNetname() if zone_net else "<unknown>"

            if zone.GetNetCode() not in net_codes_to_keep:
                zones_to_remove.append(zone)
                logger.debug(
                    f"  Removing zone on net '{zone_net_name}' (not in target nets)"
                )
            else:
                zones_kept.append(zone_net_name)
                logger.debug(f"  Keeping zone on net '{zone_net_name}'")

        if zones_kept:
            logger.debug(f"  Zones kept for nets: {zones_kept}")

    for zone in zones_to_remove:
        new_board.RemoveNative(zone)

    logger.debug(
        f"  Zone processing: {total_zones} total, {len(zones_to_remove)} removed, "
        f"{total_zones - len(zones_to_remove)} kept"
    )

    # Remove drawings (text, shapes) on copper layers unless processing no-net
    # Text elements don't have nets, so they should only appear in no-net SVG
    drawings_to_remove = []
    processing_no_net = "<no_net>" in net_names

    for drawing in new_board.GetDrawings():
        # Check if drawing is on a copper layer
        drawing_layer = drawing.GetLayer()
        is_on_copper = drawing_layer in (pcbnew.F_Cu, pcbnew.B_Cu) or (
            drawing_layer >= pcbnew.In1_Cu and drawing_layer <= pcbnew.In30_Cu
        )

        if is_on_copper and not processing_no_net:
            # Remove drawings on copper layers unless we're processing no-net
            drawings_to_remove.append(drawing)

    for drawing in drawings_to_remove:
        new_board.RemoveNative(drawing)

    # Save the modified board
    new_board.Save(str(output_file))


def create_multi_net_pcb(
    pcb_file: Path,
    net_names: list[str],
    output_file: Optional[Path] = None,
    *,
    skip_zones: bool = False,
) -> Path:
    """Create a PCB file with only specified nets."""
    if output_file is None:
        # Create temporary file
        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        os.close(fd)
        output_file = Path(temp_path)

    create_filtered_pcb(pcb_file, set(net_names), output_file, skip_zones=skip_zones)
    return output_file


def get_enabled_layers_from_pcb(pcb_file_path: str) -> list[str]:
    """Get list of enabled layers from a PCB file.

    Args:
        pcb_file_path: Path to the .kicad_pcb file

    Returns:
        List of enabled layer names

    Raises:
        RuntimeError: If PCB file cannot be loaded
    """
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
                logger.debug(f"Layer '{layer_name}' not recognized by board: {e}")
                continue

        return layer_names

    except Exception as e:
        msg = f"Error reading layers from PCB file: {e}"
        raise RuntimeError(msg) from e


def filter_layers_by_pcb_availability(
    layer_names: list[str], pcb_file_path: Optional[str] = None
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
        logger.warning(f"Could not detect PCB layers, processing all requested: {e}")
        return layer_names
