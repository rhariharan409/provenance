from app.routers.health import router as health_router
from app.routers.auth import router as auth_router
from app.routers.projects import router as projects_router
from app.routers.analysis import router as analysis_router
from app.routers.passports import router as passports_router
from app.routers.disputes import router as disputes_router
from app.routers.admin import router as admin_router
from app.routers.faculty import router as faculty_router
from app.routers.export import router as export_router
from app.routers.summaries import router as summaries_router
from app.routers.originality import router as originality_router
from app.routers.account import router as account_router

__all__ = [
    "health_router",
    "auth_router",
    "projects_router",
    "analysis_router",
    "passports_router",
    "disputes_router",
    "admin_router",
    "faculty_router",
    "export_router",
    "summaries_router",
    "originality_router",
    "account_router",
]
