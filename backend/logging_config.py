"""Centralized logging configuration for backend modules."""
import logging

from google.cloud import logging as cloud_logging

_configured = False


def _configure_logging() -> None:
    """Configure Cloud Logging once with a fallback to standard logging."""
    global _configured
    if _configured:
        return

    try:
        client = cloud_logging.Client()
        client.setup_logging()
    except Exception as exc:  # pragma: no cover - best effort fallback
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning("Cloud logging unavailable: %s", exc)
    finally:
        _configured = True


def get_logger(name: str = __name__) -> logging.Logger:
    """Return a logger with centralized Cloud Logging configuration."""
    _configure_logging()
    return logging.getLogger(name)


# Expose a module-level logger for convenience when importing this module.
logger = get_logger(__name__)
