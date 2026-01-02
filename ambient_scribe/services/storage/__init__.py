# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Storage utilities and exports."""
from typing import Optional

from ambient_scribe.services.storage.local_storage import StorageManager
from ambient_scribe.services.storage.s3_storage import S3StorageManager

__all__ = [
    "StorageManager",
    "S3StorageManager",
    "storage_manager",
    "get_storage_manager",
]

# Global storage manager instance
storage_manager = StorageManager()


def get_storage_manager(
    backend: str = "local",
    bucket_name: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    use_ssl: bool = True,
) -> StorageManager | S3StorageManager:
    """
    Get storage manager based on backend type.

    Args:
        backend: Storage backend type ('local' or 's3')
        bucket_name: S3 bucket name (required for S3)
        endpoint_url: MinIO/S3 endpoint URL
        access_key: S3 access key
        secret_key: S3 secret key
        use_ssl: Whether to use SSL

    Returns:
        StorageManager or S3StorageManager instance
    """
    if backend == "s3":
        if not bucket_name:
            raise ValueError("bucket_name is required for S3 backend")
        return S3StorageManager(
            bucket_name=bucket_name,
            endpoint_url=endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
            use_ssl=use_ssl,
        )
    else:
        return storage_manager
