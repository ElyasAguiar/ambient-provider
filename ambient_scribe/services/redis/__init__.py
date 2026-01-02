# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Redis client utilities and exports."""
import redis.asyncio as redis

from ambient_scribe.services.redis.job_manager import RedisJobManager
from ambient_scribe.services.redis.publisher import RedisPublisher
from ambient_scribe.services.redis.subscriber import RedisSubscriber

__all__ = [
    "RedisJobManager",
    "RedisPublisher",
    "RedisSubscriber",
    "get_redis_client",
    "close_redis_client",
]


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
