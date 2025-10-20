# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI main application module."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pathlib import Path

from ambient_scribe.routers import health, transcribe, notes, templates

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Ambient Scribe API",
    description="Professional medical transcription and note generation API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
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
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(transcribe.router, prefix="/api/transcribe", tags=["transcription"])
app.include_router(notes.router, prefix="/api/notes", tags=["notes"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Ambient Scribe API", "version": "0.1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ambient_scribe.main:app", host="0.0.0.0", port=8000, reload=True)
