"""
Main application entry point for the FastAPI backend.
Configures CORS, registers modular routers, and initializes the server.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.health import router as health_router
from app.routes.upload import router as upload_router
from app.routes.analyze import router as analyze_router
from app.routes.config import router as config_router
from app.routes.evaluations import router as evaluations_router
from app.services.database import init_db
from app.services.migration import run_migrations
from app.config import OLLAMA_BASE_URL, LLM_MODEL

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
# Health routes will be accessible at: /api/health and /api/health/llm
app.include_router(health_router)
# Proposal upload route: /api/upload
app.include_router(upload_router)
# Proposal analysis route: /api/analyze
app.include_router(analyze_router)
# Session config route: /api/config
app.include_router(config_router)
# Evaluations + analytics routes: /api/evaluations, /api/analytics
app.include_router(evaluations_router)


@app.on_event("startup")
def on_startup():
    """Initialise the SQLite database and apply schema migrations."""
    init_db()
    run_migrations()




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
