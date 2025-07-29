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
import re
import shutil
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


def get_board_bounding_box(pcb_file: Path) -> pcbnew.BOX2I:
    """Get the bounding box from the original PCB file.

    This is used to set consistent aux origin across all intermediate PCB files
    for proper coordinate system alignment when using SetUseAuxOrigin(True).

    Args:
        pcb_file: Path to the original PCB file

    Returns:
        pcbnew.BOX2I: Bounding box
    """
    board = load_board(pcb_file)
    bbox = board.ComputeBoundingBox(False)  # True = use board edges only
    # creating copy because original gets freed when board scope ends
    bbox_copy = pcbnew.BOX2I()
    bbox_copy.SetOrigin(bbox.GetOrigin())
    bbox_copy.SetWidth(bbox.GetWidth())
    bbox_copy.SetHeight(bbox.GetHeight())
    logger.debug(f"Computed bounding box from {pcb_file.name}: {bbox_copy.Format()}")
    return bbox_copy


def is_pcb_smaller_than_kicad_limit(pcb_file: Path) -> tuple[bool, float, float]:
    """Check if PCB dimensions are smaller than KiCad's minimum page size limit.

    KiCad refuses to respect page sizes smaller than 25.4x25.4mm, so we need
    to handle this case by forcing SVG dimensions during merge.

    Args:
        pcb_file: Path to the PCB file

    Returns:
        tuple: (is_smaller, width_mm, height_mm)
    """
    bbox = get_board_bounding_box(pcb_file)
    width_mm = pcbnew.ToMM(bbox.GetWidth())
    height_mm = pcbnew.ToMM(bbox.GetHeight())

    # KiCad minimum page size is 25.4mm x 25.4mm (1 inch x 1 inch)
    kicad_min_size_mm = 25.4
    is_smaller = width_mm < kicad_min_size_mm or height_mm < kicad_min_size_mm

    if is_smaller:
        logger.debug(
            f"PCB dimensions {width_mm:.1f}x{height_mm:.1f}mm are smaller than "
            f"KiCad limit {kicad_min_size_mm}mm"
        )

    return is_smaller, width_mm, height_mm


def get_pcb_forced_svg_params(
    pcb_file: Path,
) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Get forced SVG parameters when PCB is smaller than KiCad's page size limit.

    Args:
        pcb_file: Path to the PCB file

    Returns:
        tuple: (needs_forcing, forced_width, forced_height, forced_viewbox)
    """
    bbox = get_board_bounding_box(pcb_file)
    width_mm = pcbnew.ToMM(bbox.GetWidth())
    height_mm = pcbnew.ToMM(bbox.GetHeight())

    # KiCad minimum page size is 25.4mm x 25.4mm (1 inch x 1 inch)
    kicad_min_size_mm = 25.4
    needs_forcing = width_mm < kicad_min_size_mm or height_mm < kicad_min_size_mm

    if not needs_forcing:
        return False, None, None, None

    # Calculate the viewBox based on the actual bounding box coordinates
    # When using aux origin, the viewBox should start from (0,0) and span the PCB
    # dimensions
    forced_width = f"{width_mm:.3f}mm"
    forced_height = f"{height_mm:.3f}mm"
    forced_viewbox = f"0 0 {width_mm:.3f} {height_mm:.3f}"

    logger.debug(
        f"PCB {width_mm:.1f}x{height_mm:.1f}mm needs forced SVG params: "
        f"{forced_width}x{forced_height} viewBox={forced_viewbox}"
    )

    return True, forced_width, forced_height, forced_viewbox


def set_pcb_aux_origin_and_page_size(
    pcb_file: Path, aux_origin, page_width: int, page_height: int
) -> None:
    """Set aux origin using API and page size using file modification.

    Args:
        pcb_file: PCB file path to modify
        aux_origin: Aux origin point (pcbnew.VECTOR2I)
        page_width: Page width in nanometers
        page_height: Page height in nanometers
    """
    logger.debug(f"Setting aux origin and page size: {pcb_file.name}")
    logger.debug(f"  Setting aux origin: {aux_origin}")

    # Load the board and set aux origin using API
    board = load_board(pcb_file)
    board.GetDesignSettings().SetAuxOrigin(aux_origin)
    board.Save(str(pcb_file))

    # Read the PCB file content
    content = pcb_file.read_text()

    page_width_mm = pcbnew.ToMM(page_width)
    page_height_mm = pcbnew.ToMM(page_height)

    logger.debug(f"  Setting page size: {page_width_mm}x{page_height_mm}mm")

    # Replace page size - look for (paper .*) pattern
    page_pattern = r"\(paper .*\)"
    new_page = f'(paper "User" {page_width_mm} {page_height_mm})'
    content = re.sub(page_pattern, new_page, content)

    # Write back to file
    pcb_file.write_text(content)


def create_pcb_fitting_to_bbox(pcb_file: Path, output_file: Path) -> None:
    """Create a copy of PCB file with aux origin and page size set to match bbox."""
    logger.debug(
        f"Creating PCB copy with aux origin: {pcb_file.name} -> {output_file.name}"
    )

    # Create a copy of the board by copying the original file first
    shutil.copy2(pcb_file, output_file)

    bbox = get_board_bounding_box(pcb_file)

    # Set aux origin using API and page size using file modification
    set_pcb_aux_origin_and_page_size(
        output_file, bbox.GetOrigin(), bbox.GetWidth(), bbox.GetHeight()
    )

    # Clean up unnecessary project files created by KiCad
    prl_file = output_file.with_suffix(".kicad_prl")
    pro_file = output_file.with_suffix(".kicad_pro")
    if prl_file.exists():
        prl_file.unlink()
    if pro_file.exists():
        pro_file.unlink()


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
    use_aux_origin=None,
) -> None:
    """Create a new PCB file with only the specified nets.

    Args:
        pcb_file: Source PCB file path
        net_names: Set of net names to keep
        output_file: Output PCB file path
        skip_zones: If True, remove zones from the output
        aux_origin: Optional aux origin point to set in the filtered PCB
    """
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

    if use_aux_origin:
        bbox = get_board_bounding_box(pcb_file)
        set_pcb_aux_origin_and_page_size(
            output_file, bbox.GetOrigin(), bbox.GetWidth(), bbox.GetHeight()
        )

    # Clean up unnecessary project files created by KiCad
    prl_file = output_file.with_suffix(".kicad_prl")
    pro_file = output_file.with_suffix(".kicad_pro")
    if prl_file.exists():
        prl_file.unlink()
    if pro_file.exists():
        pro_file.unlink()


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


def generate_svg_from_board(
    board_file: Path,
    layers: str,
    output_dir: Path,
    *,
    skip_through_holes: bool = False,
    use_aux_origin: bool = True,
) -> list[Path]:
    """Generate SVG files from a PCB file using pcbnew plotting API.

    This implementation follows the plot_plan approach from kicad-kbplacer reference
    to ensure proper color handling and layer processing.

    Args:
        board_file: Path to PCB file to plot
        layers: Comma-separated layer names (e.g., "F.Cu" or "F.Cu,B.Cu")
        output_dir: Output directory for generated SVG files
        skip_through_holes: If True, hide drill marks/through holes in output
        use_aux_origin: If True, use aux origin for consistent coordinate system

    Returns:
        List of generated SVG file paths
    """
    logger.debug(f"Generating SVG from PCB file: {board_file.name}")
    logger.debug(f"  Layers: {layers}")
    logger.debug(f"  Output directory: {output_dir}")

    # Load board directly from provided location
    board = load_board(board_file)
    logger.debug(f"  Loaded board: {board_file.name}")

    # Only set aux origin if use_aux_origin is enabled
    # Note: The aux origin should already be set in the PCB file if using fit-to-content
    if use_aux_origin:
        logger.debug("  Using aux origin for coordinate system alignment")

    # Parse layer names and create plot_plan (layer_name -> layer_id mapping)
    layer_names = [layer.strip() for layer in layers.split(",")]
    plot_plan = []

    for layer_name in layer_names:
        try:
            # Get layer ID from board
            layer_id = board.GetLayerID(layer_name)
            plot_plan.append((layer_name, layer_id))
            logger.debug(f"  Added to plot_plan: '{layer_name}' -> ID {layer_id}")
        except Exception as e:
            logger.warning(f"Could not map layer '{layer_name}' to layer ID: {e}")
            continue

    if not plot_plan:
        msg = f"No valid layers found for plotting: {layers}"
        raise RuntimeError(msg)

    # Create plot controller
    plot_controller = pcbnew.PLOT_CONTROLLER(board)

    # Get the plot options and configure them
    plot_opts = plot_controller.GetPlotOptions()
    plot_opts.SetUseAuxOrigin(use_aux_origin)

    # Configure SVG-specific parameters following kicad-kbplacer approach
    plot_opts.SetFormat(pcbnew.PLOT_FORMAT_SVG)
    # Set output directory (use absolute path to be sure)
    plot_opts.SetOutputDirectory(str(output_dir.absolute()))

    # Set color settings - try default since kicad-cli said "user" not found
    try:
        color_settings = pcbnew.GetSettingsManager().GetColorSettings("user")
        logger.debug(f"  Using 'user' color settings: {color_settings}")
    except Exception:
        # Fallback to default color settings (kicad-cli uses PCB Editor settings)
        color_settings = pcbnew.GetSettingsManager().GetColorSettings()
        logger.debug(f"  Using default color settings: {color_settings}")

    plot_opts.SetColorSettings(color_settings)

    # Configure plotting options to match kicad-cli behavior
    plot_opts.SetPlotFrameRef(False)  # No drawing sheet
    plot_opts.SetPlotValue(True)  # Plot component values
    plot_opts.SetPlotReference(True)  # Plot component references
    plot_opts.SetMirror(False)  # No mirroring
    # Configure drill marks based on skip_through_holes parameter
    if skip_through_holes:
        plot_opts.SetDrillMarksType(pcbnew.DRILL_MARKS_NO_DRILL_SHAPE)
    else:
        plot_opts.SetDrillMarksType(pcbnew.DRILL_MARKS_FULL_DRILL_SHAPE)

    # Set line width for plotting
    plot_opts.SetWidthAdjust(0)  # No line width adjustment

    # Set SVG precision and units
    plot_opts.SetSvgPrecision(4)

    # Configure hole filtering
    plot_opts.SetSkipPlotNPTH_Pads(False)
    plot_opts.SetSketchPadsOnFabLayers(False)

    try:
        generated_svgs = []

        # Plot each layer separately
        for layer_name, layer_id in plot_plan:
            # Generate clean filename for this layer
            layer_filename = f"{layer_name.replace('.', '_')}_layer"

            # Open plot file for this layer
            if not plot_controller.OpenPlotfile(
                layer_filename, pcbnew.PLOT_FORMAT_SVG, ""
            ):
                msg = f"Failed to open plot file for layer {layer_name}"
                raise RuntimeError(msg)

            # Enable color mode and plot
            plot_controller.SetColorMode(True)
            logger.debug(
                f"  Color mode enabled for layer {layer_name} (ID: {layer_id})"
            )

            # Use PlotLayers for single layer because plotting drill marks
            # option is ignored if PlotLayer used
            sequence = pcbnew.LSEQ()
            sequence.append(layer_id)
            plot_controller.PlotLayers(sequence)
            logger.debug(f"  Layer {layer_name} plotted")
            plot_controller.ClosePlot()

            # Find the generated SVG file in output directory
            # PLOT_CONTROLLER may create files with board name prefix
            board_name = board.GetFileName()
            if board_name:
                board_stem = Path(board_name).stem
                expected_svg = output_dir / f"{board_stem}-{layer_filename}.svg"
            else:
                expected_svg = output_dir / f"{layer_filename}.svg"

            if expected_svg.exists():
                generated_svgs.append(expected_svg)
                logger.debug(f"  Found generated SVG: {expected_svg.name}")
            else:
                # Fallback: look for any SVG files that might have been created
                svg_pattern = f"*{layer_filename}*.svg"
                matching_svgs = list(output_dir.glob(svg_pattern))
                if matching_svgs:
                    generated_svgs.append(matching_svgs[0])
                    logger.debug(f"  Found fallback SVG: {matching_svgs[0].name}")
                else:
                    logger.warning(f"No SVG file found for layer {layer_name}")

        if not generated_svgs:
            msg = f"No SVG files were generated for layers: {layers}"
            raise RuntimeError(msg)

        logger.debug(
            f"  Successfully generated {len(generated_svgs)} SVG files in {output_dir}"
        )
        return generated_svgs

    except Exception as e:
        # Clean up on error
        try:
            plot_controller.ClosePlot()
        except Exception:
            # Ignore cleanup errors - plot controller may already be closed
            logger.debug("Plot controller cleanup failed (may already be closed)")
        msg = f"Failed to generate SVG using PLOT_CONTROLLER: {e}"
        raise RuntimeError(msg) from e

    finally:
        # No need to restore working directory since we didn't change it
        pass
