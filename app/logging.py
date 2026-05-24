import logging

from app.config.settings import LogSettings


def setup_logging(settings: LogSettings) -> None:
    logging.basicConfig(level=settings.level, format=settings.format, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(settings.level)
