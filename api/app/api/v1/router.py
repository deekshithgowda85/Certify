from fastapi import APIRouter

from app.api.v1 import auth, health, job_batches, jobs, metrics, public_batches, public_jobs

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(metrics.router)
api_router.include_router(jobs.router)
api_router.include_router(job_batches.router)
api_router.include_router(public_jobs.router)
api_router.include_router(public_batches.router)
