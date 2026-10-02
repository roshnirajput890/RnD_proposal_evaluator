"""
Health check route module.
Provides an endpoint to verify that the backend server is operational.
"""
from fastapi import APIRouter

# Initialize the router with a prefix of '/api'
router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
def get_health_status():
    """
    Health check endpoint.
    Returns:
        dict: A JSON object with the current backend status.
        Example: {"status": "ok"}
    """
    return {"status": "ok"}
