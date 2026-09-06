"""
Application logging.

The packaged .exe runs without a console, so anything printed to stdout is
lost. Every module logs through the standard logging module instead, and
setup_logging() sends records to a rotating file (plus stderr when one
exists, e.g. when run from a terminal).

Log location (first that works):
  %LOCALAPPDATA%\\MTG-Stories\\mtg-stories.log   (Windows)
  ~/.mtg-stories/mtg-stories.log                (elsewhere / fallback)
"""

import logging
import logging.handlers
import os
import sys

LOG_NAME = "mtg-stories.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3

LOG_PATH: str | None = None


def _log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA")
    if base and os.path.isdir(base):
        return os.path.join(base, "MTG-Stories")
    return os.path.join(os.path.expanduser("~"), ".mtg-stories")


def setup_logging(level: int = logging.INFO) -> str | None:
    """
    Configure the root logger once. Returns the log file path, or None if no
    writable location was found (stderr logging still works in that case).
    """
    global LOG_PATH
    root = logging.getLogger()
    if root.handlers:
        return LOG_PATH

    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    try:
        log_dir = _log_dir()
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, LOG_NAME)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
        LOG_PATH = path
    except OSError:
        LOG_PATH = None

    # PyInstaller windowed builds have no stderr
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)

    # Third-party chatter is not useful at INFO
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    return LOG_PATH
