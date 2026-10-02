"""
Routes package: contains API router modules.
"""
from app.routes.health import router as health_router
from app.routes.upload import router as upload_router

__all__ = ["health_router", "upload_router"]
