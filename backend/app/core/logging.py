from __future__ import annotations

import logging
import sys


def configure_logging() -> None:
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(handler)

    logger.propagate = False


__all__ = ["configure_logging"]
