from fastapi import FastAPI
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

app = FastAPI(
    title="Provenance API",
    description="Evidence-backed contribution analysis API",
    version="0.1.0"
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
