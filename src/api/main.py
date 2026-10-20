"""FastAPI application entrypoint for LocalRoster v2."""
import os
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.db.session import engine, Base
from src.db.seed import init_db, seed_standard_hospital
from src.api.routes_departments import router as dept_router
from src.api.routes_employees import router as emp_router
from src.api.routes_roster import router as roster_router
from src.api.routes_export import router as export_router
from src.api.routes_import import router as import_router
from src.api.routes_analytics import router as analytics_router
from src.api.routes_mcp import router as mcp_router

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema and seed initial scenario
    init_db()
    seed_standard_hospital()
    yield

app = FastAPI(
    title="LocalRoster v2 API",
    description="Dynamic Offline Workforce Roster Planner with CP-SAT Mathematical Solver",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(dept_router)
app.include_router(emp_router)
app.include_router(roster_router)
app.include_router(export_router)
app.include_router(import_router)
app.include_router(analytics_router)
app.include_router(mcp_router)

# Serve UI Static Assets
if os.path.exists(UI_DIR):
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(UI_DIR, "index.html"))
