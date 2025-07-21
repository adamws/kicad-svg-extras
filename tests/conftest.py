# SPDX-FileCopyrightText: 2025-present adamws <adamws@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT
"""Root pytest configuration."""


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--generate-references",
        action="store_true",
        default=False,
        help="Generate reference files from test outputs for later human verification",
    )
