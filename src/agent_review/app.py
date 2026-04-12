from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_review.config import Settings
from agent_review.database import create_engine, create_session_factory
from agent_review.observability import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    yield
    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(title="Agent Review", lifespan=lifespan)
    app.state.settings = settings

    from agent_review.api.health import router as health_router
    from agent_review.api.scan import router as scan_router
    from agent_review.api.webhooks import router as webhooks_router
    from agent_review.web.routes import router as web_router

    app.include_router(health_router)
    app.include_router(scan_router, prefix="/api")
    app.include_router(webhooks_router, prefix="/webhooks")
    app.include_router(web_router)
    return app
