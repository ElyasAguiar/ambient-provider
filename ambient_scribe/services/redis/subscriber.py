# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Redis subscriber for job status updates."""
import json
from typing import Any, AsyncGenerator, Dict

import redis.asyncio as redis


class RedisSubscriber:
    """Subscribes to job status updates via Redis pub/sub."""

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize Redis subscriber.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client

    async def subscribe_to_job(self, job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to job status updates.

        Args:
            job_id: Unique job identifier

        Yields:
            Status update messages
        """
        channel = f"transcription:status:{job_id}"
        pubsub = self.redis.pubsub()

        try:
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield data

                    # Stop listening after completion or failure
                    if data.get("status") in ["completed", "failed"]:
                        break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
