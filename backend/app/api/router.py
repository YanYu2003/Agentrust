"""
API router aggregation.
"""

from fastapi import APIRouter
from app.api.ca import router as ca_router
from app.api.resources import router as resources_router
from app.api.delegation import router as delegation_router, agents_router
from app.api.audit import router as audit_router

api_router = APIRouter(prefix="/api/v1")

# Include all routers
api_router.include_router(ca_router)
api_router.include_router(resources_router)
api_router.include_router(delegation_router)
api_router.include_router(agents_router)
api_router.include_router(audit_router)
