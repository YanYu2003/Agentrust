"""
Agentrust - Agent Identity and Permission System
Backend Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_database

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events handler."""
    # Startup
    logger.info("Starting Agentrust Backend...")
    await init_database()
    logger.info("Database initialized successfully")
    yield
    # Shutdown
    logger.info("Shutting down Agentrust Backend...")


app = FastAPI(
    title="Agentrust API",
    description="Agent Identity and Permission System - Based on Certificate Chain + Capability Tokens",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


# Include API routers
from app.api.router import api_router
app.include_router(api_router)
