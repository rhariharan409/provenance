from app.routers.health import router as health_router
from app.routers.auth import router as auth_router
from app.routers.projects import router as projects_router
from app.routers.analysis import router as analysis_router
from app.routers.passports import router as passports_router
from app.routers.disputes import router as disputes_router

__all__ = [
    "health_router",
    "auth_router",
    "projects_router",
    "analysis_router",
    "passports_router",
    "disputes_router",
]
