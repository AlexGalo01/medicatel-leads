from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mle.api.routes import api_router
from mle.db.base import init_db
from mle.logging_config import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Medicatel Lead Engine API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.on_event("startup")
    async def on_startup() -> None:
        await init_db()

    @app.get("/health")
    async def health_check() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()

