# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Colored logging for the application."""

import logging
import os
import sys
from typing import ClassVar


class ColoredFormatter(logging.Formatter):
    """A logging formatter that adds colors to the output."""

    COLORS: ClassVar[dict[str, str]] = {
        "WARNING": "\033[93m",  # Orange
        "ERROR": "\033[91m",  # Red
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_message = super().format(record)
        return (
            f"{self.COLORS.get(record.levelname, '')}"
            f"{log_message}{self.COLORS['RESET']}"
        )


def setup_logging(level: int = logging.INFO) -> None:
    """Set up colored logging."""
    if "NO_COLOR" in os.environ or sys.platform == "win32":
        logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter("%(levelname)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(level)
