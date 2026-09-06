"""
Application logging.

Modules log through the standard logging module. setup_logging() sends
records to stderr when one exists (running from a terminal). Nothing is
written to disk: the app must not leave files on the user's machine, and
the reasons a story failed are shown in the completion dialog anyway.
"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once. Safe to call more than once."""
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    # PyInstaller windowed builds have no stderr; then records are dropped
    if sys.stderr is not None:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(fmt)
        root.addHandler(handler)
    else:
        root.addHandler(logging.NullHandler())

    # Third-party chatter is not useful at INFO
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
