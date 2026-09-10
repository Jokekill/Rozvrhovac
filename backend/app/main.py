"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import activities, registers, schedules, settings as settings_api, solver, views
from app.config import get_settings

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Automatická tvorba školních rozvrhů pro školu s rozsáhlou uměleckou výukou. "
        "Student je plnohodnotný plánovací zdroj, třída není nejnižší úroveň modelu."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(registers.router, prefix="/api")
app.include_router(activities.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")
app.include_router(views.router, prefix="/api")
app.include_router(solver.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
