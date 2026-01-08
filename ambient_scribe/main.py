# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI main application module."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from ambient_scribe.database import close_db, init_db
from ambient_scribe.deps import Settings, get_settings
from ambient_scribe.routers import (
    auth,
    contexts,
    health,
    notes,
    sessions,
    templates,
    transcribe_jobs,
    workspaces,
)
from ambient_scribe.services.storage import S3StorageManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    await init_db()
    
    # Initialize S3/MinIO storage manager
    settings = get_settings()
    minio_endpoint = settings.minio_endpoint
    if not minio_endpoint.startswith("http"):
        minio_endpoint = f"http://{minio_endpoint}"
    
    app.state.storage_manager = S3StorageManager(
        bucket_name=settings.minio_bucket_name,
        endpoint_url=minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        use_ssl=settings.minio_use_ssl,
    )
    
    yield
    # Shutdown
    await close_db()


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="ScribeHub API",
    description="Universal transcription and structured documentation platform",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploads/storage
uploads_dir = Path("./uploads")
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Mount uploads also at /api/uploads for consistent URL paths between dev and production
app.mount("/api/uploads", StaticFiles(directory="uploads"), name="api_uploads")

# Include routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(contexts.router)
app.include_router(workspaces.router)
app.include_router(sessions.router)
app.include_router(transcribe_jobs.router)
app.include_router(notes.router)
app.include_router(templates.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ScribeHub API - Universal Transcription & Documentation Platform",
        "version": "0.2.0",
        "docs": "/api/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ambient_scribe.main:app", host="0.0.0.0", port=8000, reload=True)
