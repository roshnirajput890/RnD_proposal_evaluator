"""
Main application entry point for the FastAPI backend.
Configures CORS, registers modular routers, and initializes the server.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.health import router as health_router
from app.routes.upload import router as upload_router

# 1. Initialize the FastAPI application instance
app = FastAPI(
    title="AI-Based Multi-Agent R&D Proposal Evaluation System API",
    description="Backend API foundation for proposal intake, evaluation agents, and synthesis.",
    version="0.1.0",
)

# 2. Configure Cross-Origin Resource Sharing (CORS)
# Allowed origins include the Vite React frontend running on port 5173
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Register modular API routers
# Health routes will be accessible at: /api/health
app.include_router(health_router)
# Proposal upload route will be accessible at: /api/upload
app.include_router(upload_router)



@app.get("/")
def read_root():
    """
    Root endpoint providing a friendly welcome message.
    """
    return {
        "message": "AI-Based Multi-Agent R&D Proposal Evaluation System API is running.",
        "health_check": "/api/health",
        "docs": "/docs",
    }
