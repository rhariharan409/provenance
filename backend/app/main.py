from fastapi import FastAPI
from app.routers import health_router, auth_router

app = FastAPI(
    title="Provenance API",
    description="Evidence-backed contribution analysis API",
    version="0.1.0"
)

# List of routers: register each router in one place for clean extensibility
ROUTERS = [
    health_router,
    auth_router,
]

for router in ROUTERS:
    app.include_router(router)
