from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

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
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
    )

    from agent_review.api.admin.policies import router as admin_policies_router
    from agent_review.api.admin.scans import router as admin_scans_router
    from agent_review.api.admin.settings import router as admin_settings_router
    from agent_review.api.admin.users import router as admin_users_router
    from agent_review.api.auth import router as auth_router
    from agent_review.api.health import router as health_router
    from agent_review.api.scan import router as scan_router
    from agent_review.api.webhooks import router as webhooks_router
    from agent_review.web.routes import router as web_router

    app.include_router(health_router)
    app.include_router(scan_router, prefix="/api")
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(admin_users_router, prefix="/api/admin/users")
    app.include_router(admin_settings_router, prefix="/api/admin/settings")
    app.include_router(admin_policies_router, prefix="/api/admin/policies")
    app.include_router(admin_scans_router, prefix="/api/admin/scans")
    app.include_router(webhooks_router, prefix="/webhooks")
    app.include_router(web_router)
    return app
