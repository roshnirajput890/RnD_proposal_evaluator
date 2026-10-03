"""
Routes package: contains API router modules.
"""
from app.routes.health import router as health_router
from app.routes.upload import router as upload_router
from app.routes.analyze import router as analyze_router

__all__ = ["health_router", "upload_router", "analyze_router"]
