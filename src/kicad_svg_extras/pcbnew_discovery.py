# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Dynamic pcbnew module discovery and import utilities.

This module provides functionality to automatically locate and import the pcbnew
module from common KiCad installation locations, even when it's not available in
the current Python environment's sys.path.

Environment Variables:
    KICAD_PCBNEW_PATH: If set, this path will be checked first for the pcbnew module.
                       If the path is invalid or doesn't contain pcbnew, import
                       will fail rather than falling back to automatic search.
"""

import logging
import os
import platform
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_python_version_paths() -> list[str]:
    """Get common Python version path patterns,
    trying current version first then others."""
    major, minor = sys.version_info[:2]

    # Start with current Python version
    current_versions = [
        f"python{major}.{minor}",
        f"python{major}{minor}",
    ]

    # Add other common Python versions (for cross-version compatibility)
    other_versions = []
    for maj in [3]:  # Python 3.x
        for min_ver in range(13, 8, -1):  # 3.13 down to 3.9
            if maj != major or min_ver != minor:  # Skip current version
                other_versions.extend(
                    [
                        f"python{maj}.{min_ver}",
                        f"python{maj}{min_ver}",
                    ]
                )

    # Add generic paths
    generic_versions = [
        f"python{major}",
        "python",
    ]

    return current_versions + other_versions + generic_versions


def get_kicad_search_paths() -> list[Path]:
    """Get list of common KiCad installation paths to search for pcbnew module.

    Returns:
        List of Path objects to search for pcbnew module
    """
    search_paths = []
    system = platform.system().lower()
    python_versions = get_python_version_paths()

    if system == "windows":
        # Windows KiCad installation paths
        program_files_paths = [
            Path("C:/Program Files/KiCad"),
            Path("C:/Program Files (x86)/KiCad"),
        ]

        # Search common KiCad version patterns
        for base_path in program_files_paths:
            if base_path.exists():
                # Look for version directories
                for version_dir in base_path.iterdir():
                    if version_dir.is_dir():
                        # Common Windows KiCad Python paths
                        search_paths.extend(
                            [
                                version_dir / "bin" / "Lib" / "site-packages",
                                version_dir / "lib" / "site-packages",
                            ]
                        )

    elif system == "darwin":  # macOS
        # macOS KiCad.app bundle paths
        app_paths = [
            Path("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework"),
            Path("/Applications/KiCad.app/Contents/Frameworks/Python.framework"),
        ]

        for app_path in app_paths:
            if app_path.exists():
                # Look for Python version directories
                versions_path = app_path / "Versions"
                if versions_path.exists():
                    for version_dir in versions_path.iterdir():
                        if version_dir.is_dir():
                            for py_version in python_versions:
                                search_paths.append(
                                    version_dir / "lib" / py_version / "site-packages"
                                )

        # Also check common macOS Python paths
        for py_version in python_versions:
            search_paths.extend(
                [
                    Path(f"/usr/local/lib/{py_version}/site-packages"),
                    Path(f"/opt/homebrew/lib/{py_version}/site-packages"),
                ]
            )

    else:  # Linux and other Unix-like systems
        # System-wide installation paths
        for py_version in python_versions:
            search_paths.extend(
                [
                    Path(f"/usr/lib/{py_version}/site-packages"),
                    Path(f"/usr/local/lib/{py_version}/site-packages"),
                    Path(f"/usr/lib/{py_version}/dist-packages"),  # Debian/Ubuntu
                    Path(f"/opt/kicad/lib/{py_version}/site-packages"),
                ]
            )

        # User home directory paths
        home = Path.home()
        search_paths.extend(
            [
                home / ".local" / "lib" / python_versions[0] / "site-packages",
            ]
        )

        # Flatpak KiCad installation
        flatpak_path = home / ".var" / "app" / "org.kicad.KiCad"
        if flatpak_path.exists():
            for py_version in python_versions:
                search_paths.append(
                    flatpak_path / "data" / "kicad" / py_version / "site-packages"
                )

    return search_paths


def find_pcbnew_module() -> Optional[str]:
    """Search for pcbnew module in common KiCad installation locations.

    First checks the KICAD_PCBNEW_PATH environment variable if set.
    If the environment variable is set but invalid, returns None.
    Otherwise searches common KiCad installation paths.

    Returns:
        Path to directory containing pcbnew module, or None if not found
    """
    logger.debug("Searching for pcbnew module in KiCad installations...")

    # Check environment variable first
    env_path = os.environ.get("KICAD_PCBNEW_PATH")
    if env_path:
        logger.debug(f"Checking KICAD_PCBNEW_PATH environment variable: {env_path}")
        env_path_obj = Path(env_path)

        if not env_path_obj.exists():
            logger.error(
                f"KICAD_PCBNEW_PATH points to non-existent directory: {env_path}"
            )
            return None

        # Check if pcbnew module exists in the specified path
        pcbnew_py = env_path_obj / "pcbnew.py"
        pcbnew_dir = env_path_obj / "pcbnew"
        pcbnew_pyd = env_path_obj / "pcbnew.pyd"  # Windows compiled module
        pcbnew_so = env_path_obj / "pcbnew.so"  # Linux compiled module

        if any(
            [
                pcbnew_py.exists(),
                pcbnew_dir.exists(),
                pcbnew_pyd.exists(),
                pcbnew_so.exists(),
            ]
        ):
            logger.debug(f"Found pcbnew module at KICAD_PCBNEW_PATH: {env_path}")
            return str(env_path_obj)
        else:
            logger.error(
                f"KICAD_PCBNEW_PATH set but pcbnew module not found in: {env_path}"
            )
            return None

    search_paths = get_kicad_search_paths()

    for search_path in search_paths:
        if not search_path.exists():
            continue

        logger.debug(f"Checking path: {search_path}")

        # Look for pcbnew.py or pcbnew directory
        pcbnew_py = search_path / "pcbnew.py"
        pcbnew_dir = search_path / "pcbnew"
        pcbnew_pyd = search_path / "pcbnew.pyd"  # Windows compiled module
        pcbnew_so = search_path / "pcbnew.so"  # Linux compiled module

        if any(
            [
                pcbnew_py.exists(),
                pcbnew_dir.exists(),
                pcbnew_pyd.exists(),
                pcbnew_so.exists(),
            ]
        ):
            logger.debug(f"Found pcbnew module at: {search_path}")
            return str(search_path)

    logger.debug("pcbnew module not found in any search paths")
    return None


def import_pcbnew():
    """Import pcbnew module with dynamic path discovery.

    Returns:
        The imported pcbnew module

    Raises:
        ImportError: If pcbnew module cannot be found or imported
    """
    # First, try standard import (fastest path for working environments)
    try:
        import pcbnew  # noqa: PLC0415

        logger.debug("pcbnew imported successfully from standard Python path")
        return pcbnew
    except ImportError:
        logger.debug("pcbnew not found in standard Python path, searching...")

    # Search for pcbnew in KiCad installations
    pcbnew_path = find_pcbnew_module()
    if pcbnew_path is None:
        msg = (
            "pcbnew module not found. Please ensure KiCad is installed with "
            "Python bindings. Common installation paths have been searched but "
            "pcbnew was not located. You may need to install KiCad, set the "
            "KICAD_PCBNEW_PATH environment variable to the directory containing "
            "the pcbnew module, or add its Python path manually."
        )
        raise ImportError(msg)

    # Add found path to sys.path and try import
    if pcbnew_path not in sys.path:
        sys.path.insert(0, pcbnew_path)
        logger.debug(f"Added to sys.path: {pcbnew_path}")

    # On Windows, add potential KiCad DLL directories for native module loading
    dll_dirs_added = []
    if platform.system().lower() == "windows":
        # Get parent directory of pcbnew_path and look for bin directory
        pcbnew_parent = Path(pcbnew_path).parent
        potential_dll_dirs = [
            pcbnew_parent / "bin",  # Common KiCad structure
            pcbnew_parent,  # Sometimes DLLs are in same directory
            pcbnew_parent / "..",  # Look one level up
        ]

        for dll_dir in potential_dll_dirs:
            if dll_dir.exists() and dll_dir.is_dir():
                try:
                    # os.add_dll_directory is available in Python 3.8+
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(str(dll_dir))
                        dll_dirs_added.append(str(dll_dir))
                        logger.debug(f"Added DLL directory: {dll_dir}")
                except OSError as e:
                    logger.debug(f"Failed to add DLL directory {dll_dir}: {e}")

    try:
        import pcbnew  # noqa: PLC0415

        logger.debug(f"pcbnew imported successfully from: {pcbnew_path}")
        if dll_dirs_added:
            logger.debug(f"Used DLL directories: {dll_dirs_added}")
        return pcbnew
    except ImportError as e:
        msg = (
            f"Found pcbnew at {pcbnew_path} but failed to import it: {e}. "
            "This may indicate a KiCad installation issue or Python version mismatch."
        )
        if platform.system().lower() == "windows":
            msg += (
                " On Windows, this often means KiCad's DLL dependencies cannot be "
                "found. Try setting KICAD_PCBNEW_PATH to the directory containing "
                "both pcbnew.py and the KiCad DLLs, or ensure KiCad's bin "
                "directory is in your PATH."
            )
        raise ImportError(msg) from e


def get_pcbnew_info() -> dict[str, str]:
    """Get information about the discovered pcbnew installation.

    Returns:
        Dictionary with pcbnew installation information
    """
    info = {}

    try:
        pcbnew = import_pcbnew()
        info["version"] = pcbnew.Version()
        info["path"] = pcbnew.__file__ if hasattr(pcbnew, "__file__") else "unknown"
        info["discovery_path"] = "dynamic discovery"
    except ImportError as e:
        info["error"] = str(e)

    return info
