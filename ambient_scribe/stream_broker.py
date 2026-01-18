"""FastStream broker configuration for Redis Streams."""

import logging

from faststream import FastStream
from faststream.redis import RedisBroker

from ambient_scribe.deps import get_settings

logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Initialize Redis broker with streams configuration
broker = RedisBroker(settings.redis_url)

# Initialize FastStream app
app = FastStream(broker)

# Import consumers to register handlers
from ambient_scribe.consumers import result_consumer  # noqa: E402,F401


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
