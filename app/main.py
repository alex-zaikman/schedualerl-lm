import logging
from contextlib import asynccontextmanager

import httpx
from apscheduler import AsyncScheduler
from fastapi import FastAPI

from app.auth.middleware import AuthMiddleware
from app.config.settings import Settings, get_settings
from app.db.engine import create_db
from app.db.scope import register_row_scope_events
from app.logging import setup_logging
from app.routes.api import router as api_router
from app.routes.health import router as health_router
from app.routes.tasks import router as tasks_router
from app.scheduler.service import configure_scheduler, create_scheduler

logger = logging.getLogger(__name__)


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, session_factory = await create_db(settings.db)
        app.state.engine = engine
        app.state.session_factory = session_factory

        scheduler: AsyncScheduler = create_scheduler(engine, settings)
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.scheduler.webhook_timeout_seconds)
        )

        async with scheduler:
            await configure_scheduler(scheduler, session_factory, settings, http_client)
            await scheduler.start_in_background()
            app.state.scheduler = scheduler
            logger.info("Application startup complete")
            try:
                yield
            finally:
                await http_client.aclose()

        await engine.dispose()
        logger.info("PostgreSQL engine disposed")

    app = FastAPI(title=settings.app.name, debug=settings.app.debug, lifespan=lifespan)
    app.add_middleware(AuthMiddleware, settings=settings)
    app.include_router(health_router)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    return app


settings = get_settings()
setup_logging(settings.log)
register_row_scope_events()
logger.info("Starting %s", settings.app.name)

app = create_app(settings)
