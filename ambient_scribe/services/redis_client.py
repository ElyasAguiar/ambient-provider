# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Redis client for job queue and pub/sub messaging."""
import json
from datetime import timedelta
from typing import Any, AsyncGenerator, Dict, Optional

import redis.asyncio as redis
from redis.asyncio.client import PubSub


class RedisJobManager:
    """Manages job status and metadata in Redis with TTL."""

    def __init__(self, redis_client: redis.Redis, default_ttl: int = 3600):
        """
        Initialize Redis job manager.

        Args:
            redis_client: Redis async client
            default_ttl: Default TTL in seconds (default: 3600 = 1 hour)
        """
        self.redis = redis_client
        self.default_ttl = default_ttl

    async def create_job(self, job_id: str, initial_data: Dict[str, Any]) -> bool:
        """
        Create a new job entry in Redis.

        Args:
            job_id: Unique job identifier
            initial_data: Initial job data (status, progress, etc.)

        Returns:
            True if successful
        """
        key = f"job:{job_id}:status"
        data = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            **initial_data,
        }

        await self.redis.set(key, json.dumps(data), ex=self.default_ttl)
        return True

    async def update_job_status(
        self, job_id: str, status: str, progress: Optional[int] = None, **kwargs
    ) -> bool:
        """
        Update job status in Redis.

        Args:
            job_id: Unique job identifier
            status: Job status (queued, processing, completed, failed)
            progress: Optional progress percentage (0-100)
            **kwargs: Additional fields to update

        Returns:
            True if successful
        """
        key = f"job:{job_id}:status"

        # Get current data
        current_data = await self.get_job_status(job_id)
        if current_data is None:
            current_data = {"job_id": job_id}

        # Update fields
        current_data["status"] = status
        if progress is not None:
            current_data["progress"] = progress
        current_data.update(kwargs)

        # Save with TTL reset
        await self.redis.set(key, json.dumps(current_data), ex=self.default_ttl)
        return True

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job status from Redis.

        Args:
            job_id: Unique job identifier

        Returns:
            Job data dictionary or None if not found
        """
        key = f"job:{job_id}:status"
        data = await self.redis.get(key)

        if data is None:
            return None

        return json.loads(data)

    async def delete_job(self, job_id: str) -> bool:
        """
        Delete job from Redis.

        Args:
            job_id: Unique job identifier

        Returns:
            True if successful
        """
        key = f"job:{job_id}:status"
        result = await self.redis.delete(key)
        return result > 0

    async def set_job_result(self, job_id: str, result: Dict[str, Any]) -> bool:
        """
        Store job result in Redis.

        Args:
            job_id: Unique job identifier
            result: Result data to store

        Returns:
            True if successful
        """
        key = f"job:{job_id}:result"
        await self.redis.set(key, json.dumps(result), ex=self.default_ttl)
        return True

    async def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job result from Redis.

        Args:
            job_id: Unique job identifier

        Returns:
            Result data or None if not found
        """
        key = f"job:{job_id}:result"
        data = await self.redis.get(key)

        if data is None:
            return None

        return json.loads(data)


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


async def get_redis_client(redis_url: str) -> redis.Redis:
    """
    Create Redis client from URL.

    Args:
        redis_url: Redis connection URL (e.g., 'redis://localhost:6379/0')

    Returns:
        Redis async client
    """
    return redis.from_url(redis_url, encoding="utf-8", decode_responses=True)


async def close_redis_client(client: redis.Redis):
    """
    Close Redis client connection.

    Args:
        client: Redis async client
    """
    await client.close()
