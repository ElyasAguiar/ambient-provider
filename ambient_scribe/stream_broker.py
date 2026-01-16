# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastStream broker configuration for Redis Streams."""
import logging

from faststream import FastStream
from faststream.redis import RedisBroker

from ambient_scribe.deps import get_settings

logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Initialize Redis broker with streams configuration
broker = RedisBroker(
    url=settings.redis_url,
    # Enable graceful shutdown
    graceful_timeout=30.0,
    # Connection pool settings
    max_connections=50,
    decode_responses=False,  # We handle encoding/decoding via Pydantic
)

# Initialize FastStream app
app = FastStream(
    broker,
    title="Ambient Scribe Transcription Streams",
    description="FastStream application for managing transcription jobs and results",
    version="1.0.0",
)


@app.on_startup
async def on_startup():
    """Log startup event."""
    logger.info("FastStream broker starting...")
    logger.info(f"Connected to Redis: {settings.redis_url}")
    logger.info(f"Job stream: {settings.transcription_jobs_stream}")
    logger.info(f"Results stream: {settings.transcription_results_stream}")
    logger.info(f"DLQ stream: {settings.transcription_dlq_stream}")


@app.on_shutdown
async def on_shutdown():
    """Log shutdown event."""
    logger.info("FastStream broker shutting down...")
