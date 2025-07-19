# SPDX-FileCopyrightText: 2024-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""PCB net filtering utilities using pcbnew API."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

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
    return pcbnew.LoadBoard(str(pcb_file))


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


def get_tracks_for_net(board, net_name: str, net_codes: dict[str, int]) -> list:
    """Get all tracks for a specific net."""
    if net_name not in net_codes:
        return []

    net_code = net_codes[net_name]
    tracks = []

    for track in board.GetTracks():
        if track.GetNetCode() == net_code:
            tracks.append(track)

    return tracks


def get_vias_for_net(board, net_name: str, net_codes: dict[str, int]) -> list:
    """Get all vias for a specific net."""
    if net_name not in net_codes:
        return []

    net_code = net_codes[net_name]
    vias = []

    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA) and track.GetNetCode() == net_code:
            vias.append(track)

    return vias


def get_pads_for_net(board, net_name: str, net_codes: dict[str, int]) -> list:
    """Get all pads for a specific net."""
    if net_name not in net_codes:
        return []

    net_code = net_codes[net_name]
    pads = []

    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() == net_code:
                pads.append(pad)

    return pads


def has_elements_on_side(
    board, net_name: str, side: str, net_codes: dict[str, int]
) -> bool:
    """Check if a net has any tracks, pads, or vias on a given side."""
    if net_name not in net_codes:
        return False

    net_code = net_codes[net_name]
    cu_layer = pcbnew.F_Cu if side == "front" else pcbnew.B_Cu

    # Check for tracks and vias on the specified side
    for track in board.GetTracks():
        if track.GetNetCode() == net_code and track.IsOnLayer(cu_layer):
            return True

    # Check for pads on the specified side
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() == net_code and pad.IsOnLayer(cu_layer):
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
    if skip_zones:
        zones_to_remove = list(new_board.Zones())
    else:
        zones_to_remove = []
        for zone in new_board.Zones():
            if zone.GetNetCode() not in net_codes_to_keep:
                zones_to_remove.append(zone)

    for zone in zones_to_remove:
        new_board.RemoveNative(zone)

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
