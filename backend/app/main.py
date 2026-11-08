from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from app.config import settings
from app.routers import (
    health_router,
    auth_router,
    projects_router,
    analysis_router,
    passports_router,
    disputes_router,
    admin_router,
    faculty_router,
    export_router,
    summaries_router,
    originality_router,
    account_router,
    reviews_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure REPO_STORAGE_PATH exists and is writable at startup
    try:
        os.makedirs(settings.REPO_STORAGE_PATH, exist_ok=True)
    except Exception:
        pass
    yield


app = FastAPI(
    title="Provenance API",
    description="Evidence-backed contribution analysis API",
    version="0.1.0",
    lifespan=lifespan,
)

# List of routers: register each router in one place for clean extensibility
ROUTERS = [
    health_router,
    auth_router,
    projects_router,
    analysis_router,
    passports_router,
    disputes_router,
    admin_router,
    faculty_router,
    export_router,
    summaries_router,
    originality_router,
    account_router,
    reviews_router,
]

for router in ROUTERS:
    app.include_router(router)
