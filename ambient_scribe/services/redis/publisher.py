# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Redis publisher for job status updates."""
import json
from typing import Any, Dict, Optional

import redis.asyncio as redis


class RedisPublisher:
    """Publishes job status updates via Redis pub/sub."""

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize Redis publisher.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client

    async def publish_status_update(
        self, job_id: str, status: str, progress: Optional[int] = None, **kwargs
    ) -> int:
        """
        Publish job status update to Redis channel.

        Args:
            job_id: Unique job identifier
            status: Job status
            progress: Optional progress percentage
            **kwargs: Additional data to publish

        Returns:
            Number of subscribers that received the message
        """
        channel = f"transcription:status:{job_id}"

        message = {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            **kwargs,
        }

        return await self.redis.publish(channel, json.dumps(message))

    async def publish_progress(
        self, job_id: str, progress: int, message: Optional[str] = None
    ) -> int:
        """
        Publish progress update.

        Args:
            job_id: Unique job identifier
            progress: Progress percentage (0-100)
            message: Optional progress message

        Returns:
            Number of subscribers that received the message
        """
        return await self.publish_status_update(
            job_id, status="processing", progress=progress, message=message
        )

    async def publish_completed(self, job_id: str, result: Optional[Dict[str, Any]] = None) -> int:
        """
        Publish job completion.

        Args:
            job_id: Unique job identifier
            result: Optional result data

        Returns:
            Number of subscribers that received the message
        """
        return await self.publish_status_update(
            job_id, status="completed", progress=100, result=result
        )

    async def publish_failed(
        self, job_id: str, error: str, error_details: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Publish job failure.

        Args:
            job_id: Unique job identifier
            error: Error message
            error_details: Optional error details

        Returns:
            Number of subscribers that received the message
        """
        return await self.publish_status_update(
            job_id, status="failed", error=error, error_details=error_details
        )
