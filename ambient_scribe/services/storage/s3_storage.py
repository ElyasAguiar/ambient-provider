# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""S3/MinIO storage manager with async upload support."""
import asyncio
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Optional

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3StorageManager:
    """S3-based storage manager for MinIO or AWS S3 with async operations."""

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
        use_ssl: bool = True,
        chunk_size: int = 5 * 1024 * 1024,  # 5MB default
    ):
        """
        Initialize S3 storage manager.

        Args:
            bucket_name: S3 bucket name
            endpoint_url: MinIO/S3 endpoint (e.g., 'http://minio:9000' for MinIO)
            access_key: Access key ID
            secret_key: Secret access key
            region: AWS region
            use_ssl: Whether to use SSL/TLS
            chunk_size: Size of chunks for multipart upload (default: 5MB)
        """
        self.bucket_name = bucket_name
        self.region = region
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.use_ssl = use_ssl
        self.chunk_size = chunk_size

        # Create aioboto3 session
        self.session = aioboto3.Session()

        # Optimized configuration for async uploads
        self.config = Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "adaptive"},
            max_pool_connections=50,
            connect_timeout=10,
            read_timeout=60,
        )

        # Synchronous client for bucket initialization (runs once)
        import boto3

        sync_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
            use_ssl=use_ssl,
        )
        self._ensure_bucket_exists(sync_client)

    def _ensure_bucket_exists(self, s3_client):
        """Create bucket if it doesn't exist (synchronous, called once at init)."""
        try:
            s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                # Bucket doesn't exist, create it
                try:
                    if self.region == "us-east-1":
                        s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": self.region},
                        )
                    logger.info(f"Created bucket: {self.bucket_name}")
                except ClientError as create_error:
                    logger.error(f"Error creating bucket: {create_error}")
            else:
                logger.error(f"Error checking bucket: {e}")

    async def save_file(
        self, file_content: bytes, filename: str, subfolder: Optional[str] = None
    ) -> str:
        """
        Save file to S3/MinIO with async upload and multipart support for large files.

        Args:
            file_content: File content as bytes
            filename: Original filename
            subfolder: Optional subfolder path

        Returns:
            S3 object key (permanent path) for the uploaded file
        """
        # Generate unique filename
        file_id = str(uuid.uuid4())
        file_extension = Path(filename).suffix
        unique_filename = f"{file_id}{file_extension}"

        # Determine object key
        if subfolder:
            object_key = f"{subfolder}/{unique_filename}"
        else:
            object_key = unique_filename

        # Determine content type
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Upload to S3/MinIO asynchronously
        try:
            async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                use_ssl=self.use_ssl,
                config=self.config,
            ) as s3_client:
                # For small files (< chunk_size), upload directly
                if len(file_content) < self.chunk_size:
                    await s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=object_key,
                        Body=file_content,
                        ContentType=content_type,
                    )
                    logger.info(f"Uploaded file directly: {object_key} ({len(file_content)} bytes)")
                else:
                    # For large files, use multipart upload
                    await self._multipart_upload(
                        s3_client, file_content, object_key, content_type
                    )
                    logger.info(
                        f"Uploaded file via multipart: {object_key} ({len(file_content)} bytes)"
                    )

            # Return object key for permanent storage in database
            return object_key
        except ClientError as e:
            logger.error(f"Error uploading file to S3: {e}")
            raise Exception(f"Error uploading file to S3: {e}")

    async def _multipart_upload(
        self,
        s3_client,
        file_content: bytes,
        object_key: str,
        content_type: str,
    ):
        """Upload large files in parts for better reliability and performance.

        Args:
            s3_client: Async S3 client
            file_content: File content as bytes
            object_key: S3 object key
            content_type: MIME type of the file
        """
        # Initiate multipart upload
        response = await s3_client.create_multipart_upload(
            Bucket=self.bucket_name,
            Key=object_key,
            ContentType=content_type,
        )
        upload_id = response["UploadId"]

        parts = []
        part_number = 1

        try:
            # Upload each part
            for i in range(0, len(file_content), self.chunk_size):
                chunk = file_content[i : i + self.chunk_size]

                part_response = await s3_client.upload_part(
                    Bucket=self.bucket_name,
                    Key=object_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )

                parts.append({"PartNumber": part_number, "ETag": part_response["ETag"]})

                logger.debug(f"Uploaded part {part_number} for {object_key}")
                part_number += 1

            # Complete multipart upload
            await s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            logger.info(f"Completed multipart upload for {object_key} ({len(parts)} parts)")

        except Exception as e:
            # Abort upload in case of error
            logger.error(f"Multipart upload failed for {object_key}: {e}")
            try:
                await s3_client.abort_multipart_upload(
                    Bucket=self.bucket_name, Key=object_key, UploadId=upload_id
                )
                logger.info(f"Aborted multipart upload for {object_key}")
            except Exception as abort_error:
                logger.error(f"Failed to abort multipart upload: {abort_error}")
            raise Exception(f"Multipart upload failed: {e}")

    async def read_file(self, object_key: str) -> bytes:
        """
        Read file from S3/MinIO asynchronously.

        Args:
            object_key: S3 object key

        Returns:
            File content as bytes
        """
        try:
            async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                use_ssl=self.use_ssl,
                config=self.config,
            ) as s3_client:
                response = await s3_client.get_object(Bucket=self.bucket_name, Key=object_key)
                async with response["Body"] as stream:
                    content = await stream.read()
                    logger.debug(f"Read {len(content)} bytes from {object_key}")
                    return content
        except ClientError as e:
            logger.error(f"Error reading file from S3: {e}")
            raise Exception(f"Error reading file from S3: {e}")

    async def delete_file(self, object_key: str) -> bool:
        """
        Delete file from S3/MinIO asynchronously.

        Args:
            object_key: S3 object key

        Returns:
            True if successful
        """
        try:
            async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                use_ssl=self.use_ssl,
                config=self.config,
            ) as s3_client:
                await s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
            logger.info(f"Deleted file: {object_key}")
            return True
        except ClientError as e:
            logger.error(f"Error deleting file from S3: {e}")
            return False

    def generate_presigned_url(self, object_key: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for object access.

        Note: This method is synchronous as presigned URL generation is fast
        and doesn't benefit significantly from async operation.

        Args:
            object_key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL
        """
        try:
            # Use synchronous boto3 client for presigned URL generation
            import boto3

            sync_client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=Config(signature_version="s3v4"),
                use_ssl=self.use_ssl,
            )
            url = sync_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expiration,
            )
            logger.debug(f"Generated presigned URL for {object_key}")
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise Exception(f"Error generating presigned URL: {e}")

    async def file_exists(self, object_key: str) -> bool:
        """
        Check if file exists in S3/MinIO asynchronously.

        Args:
            object_key: S3 object key

        Returns:
            True if file exists
        """
        try:
            async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                use_ssl=self.use_ssl,
                config=self.config,
            ) as s3_client:
                await s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError:
            return False

    async def get_file_info(self, object_key: str) -> dict:
        """
        Get file information from S3/MinIO asynchronously.

        Args:
            object_key: S3 object key

        Returns:
            Dictionary with file metadata
        """
        try:
            async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                use_ssl=self.use_ssl,
                config=self.config,
            ) as s3_client:
                response = await s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
                return {
                    "filename": object_key.split("/")[-1],
                    "size": response["ContentLength"],
                    "modified": response["LastModified"],
                    "mimetype": response.get("ContentType", "application/octet-stream"),
                    "etag": response["ETag"],
                }
        except ClientError as e:
            logger.error(f"Error getting file info from S3: {e}")
            return {}
