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
    PCBNEW_AVAILABLE = True
except ImportError:
    PCBNEW_AVAILABLE = False

    # Create mock module for type hints
    class MockBoard:
        def GetNets(self):  # noqa: N802
            return []

        def GetTracks(self):  # noqa: N802
            return []

        def GetFootprints(self):  # noqa: N802
            return []

        def SaveAs(self, path):  # noqa: N802
            pass

    class MockPcbnew:
        PCB_TRACK = "PCB_TRACK"
        PCB_VIA = "PCB_VIA"
        PAD = "PAD"
        F_Cu = "F_Cu"
        B_Cu = "B_Cu"

        @staticmethod
        def LoadBoard(path):  # noqa: N802, ARG004
            return MockBoard()

    pcbnew = MockPcbnew()
    wx = None
logger = logging.getLogger(__name__)


class PCBNetFilter:
    """Filter PCB elements by net name using pcbnew API."""

    def __init__(self, pcb_file: Path, *, skip_zones: bool = False):
        if not PCBNEW_AVAILABLE:
            msg = (
                "pcbnew module not available. "
                "This package requires KiCad to be installed with Python bindings. "
                "For testing without KiCad, set KICAD_MOCK=1 environment variable."
            )
            raise ImportError(msg)
        self.pcb_file = pcb_file
        self.board = pcbnew.LoadBoard(str(pcb_file))
        self.net_codes = self._get_net_codes()
        self.skip_zones = skip_zones

    def _get_net_codes(self) -> dict[str, int]:
        """Get mapping of net name to net code."""
        net_codes = {}
        netlist = self.board.GetNetInfo()
        for net_code in range(netlist.GetNetCount()):
            net_info = netlist.GetNetItem(net_code)
            if net_info:
                net_name = net_info.GetNetname()
                net_codes[net_name] = net_code
        net_codes["<no_net>"] = 0  # Use net code 0 for no net
        return net_codes

    def get_net_names(self) -> list[str]:
        """Get all net names in the PCB."""
        return list(self.net_codes.keys())

    def get_tracks_for_net(self, net_name: str) -> list[pcbnew.PCB_TRACK]:
        """Get all tracks for a specific net."""
        if net_name not in self.net_codes:
            return []

        net_code = self.net_codes[net_name]
        tracks = []

        for track in self.board.GetTracks():
            if track.GetNetCode() == net_code:
                tracks.append(track)

        return tracks

    def get_vias_for_net(self, net_name: str) -> list[pcbnew.PCB_VIA]:
        """Get all vias for a specific net."""
        if net_name not in self.net_codes:
            return []

        net_code = self.net_codes[net_name]
        vias = []

        for track in self.board.GetTracks():
            if isinstance(track, pcbnew.PCB_VIA) and track.GetNetCode() == net_code:
                vias.append(track)

        return vias

    def get_pads_for_net(self, net_name: str) -> list[pcbnew.PAD]:
        """Get all pads for a specific net."""
        if net_name not in self.net_codes:
            return []

        net_code = self.net_codes[net_name]
        pads = []

        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetCode() == net_code:
                    pads.append(pad)

        return pads

    def has_elements_on_side(self, net_name: str, side: str) -> bool:
        """Check if a net has any tracks, pads, or vias on a given side."""
        if net_name not in self.net_codes:
            return False

        net_code = self.net_codes[net_name]
        cu_layer = pcbnew.F_Cu if side == "front" else pcbnew.B_Cu

        # Check for tracks and vias on the specified side
        for track in self.board.GetTracks():
            if track.GetNetCode() == net_code and track.IsOnLayer(cu_layer):
                return True

        # Check for pads on the specified side
        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetCode() == net_code and pad.IsOnLayer(cu_layer):
                    return True

        return False

    def create_filtered_pcb(self, net_names: set[str], output_file: Path) -> None:
        """Create a new PCB file with only the specified nets."""
        # Create a copy of the board by copying the original file first
        shutil.copy2(self.pcb_file, output_file)

        # Load the copied board
        new_board = pcbnew.LoadBoard(str(output_file))

        # Get net codes to keep
        net_codes_to_keep = {
            self.net_codes[net_name]
            for net_name in net_names
            if net_name in self.net_codes
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
        if self.skip_zones:
            zones_to_remove = list(new_board.Zones())
        else:
            zones_to_remove = []
            for zone in new_board.Zones():
                if zone.GetNetCode() not in net_codes_to_keep:
                    zones_to_remove.append(zone)

        for zone in zones_to_remove:
            new_board.RemoveNative(zone)

        # Save the modified board
        new_board.Save(str(output_file))

    def create_single_net_pcb(
        self, net_name: str, output_file: Optional[Path] = None
    ) -> Path:
        """Create a PCB file with only one net."""
        if output_file is None:
            # Create temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
            os.close(fd)
            output_file = Path(temp_path)

        self.create_filtered_pcb({net_name}, output_file)
        return output_file

    def create_multi_net_pcb(
        self, net_names: list[str], output_file: Optional[Path] = None
    ) -> Path:
        """Create a PCB file with multiple specified nets."""
        if output_file is None:
            # Create temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
            os.close(fd)
            output_file = Path(temp_path)

        self.create_filtered_pcb(set(net_names), output_file)
        return output_file
