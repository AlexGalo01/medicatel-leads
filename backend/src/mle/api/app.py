from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mle.api.routes import api_router
from mle.db.base import init_db
from mle.services.bootstrap_admin import ensure_initial_admin
from mle.logging_config import configure_logging
from mle.observability import configure_langsmith_env


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Medicatel Lead Engine API", version="0.1.0")
    # allow_credentials=True no es compatible con allow_origins=["*"] (CORS del navegador).
    # El frontend usa fetch sin cookies cross-origin; credentials en false + * cubre dev local.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.on_event("startup")
    async def on_startup() -> None:
        configure_langsmith_env()
        await init_db()
        await ensure_initial_admin()

    @app.get("/health")
    async def health_check() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()

