import logging
import sys


def configure_logging(debug: bool = False) -> None:
    """Configure application-wide logging (wired in app.main during Phase 2)."""
    root = logging.getLogger()
    if root.handlers:
        return

    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
