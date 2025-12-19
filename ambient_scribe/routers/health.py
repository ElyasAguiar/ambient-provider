# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Health check router."""
import os

from fastapi import APIRouter, Depends

from ambient_scribe.deps import get_settings
from ambient_scribe.models import HealthResponse

router = APIRouter()


@router.get("/", response_model=HealthResponse)
async def health_check(settings=Depends(get_settings)) -> HealthResponse:
    """Basic health check endpoint."""

    # Check service dependencies
    services = {}

    # Check if NVIDIA API key is configured
    if settings.nvidia_api_key:
        services["nvidia_api"] = "configured"
    else:
        services["nvidia_api"] = "not_configured"

    # Check if Riva URI is accessible (basic check)
    if settings.riva_uri:
        services["riva_asr"] = "configured"
    else:
        services["riva_asr"] = "not_configured"

    # Check templates directory
    services["templates"] = (
        "ok" if os.path.exists(settings.templates_dir) else "missing"
    )

    # Check upload directory
    services["storage"] = "ok" if os.path.exists(settings.upload_dir) else "missing"

    return HealthResponse(
        status="healthy", version=settings.api_version, services=services
    )
