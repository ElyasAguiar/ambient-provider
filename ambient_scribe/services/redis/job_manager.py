# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Redis job manager for job status and metadata."""
import json
from typing import Any, Dict, Optional

import redis.asyncio as redis


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
