# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""S3/MinIO storage manager."""
import mimetypes
import uuid
from pathlib import Path
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class S3StorageManager:
    """S3-based storage manager for MinIO or AWS S3."""

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
        use_ssl: bool = True,
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
        """
        self.bucket_name = bucket_name
        self.region = region

        # Initialize boto3 S3 client
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
            use_ssl=use_ssl,
        )

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                # Bucket doesn't exist, create it
                try:
                    if self.region == "us-east-1":
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": self.region},
                        )
                except ClientError as create_error:
                    print(f"Error creating bucket: {create_error}")
            else:
                print(f"Error checking bucket: {e}")

    async def save_file(
        self, file_content: bytes, filename: str, subfolder: Optional[str] = None
    ) -> str:
        """
        Save file to S3/MinIO.

        Args:
            file_content: File content as bytes
            filename: Original filename
            subfolder: Optional subfolder path

        Returns:
            S3 object key (path)
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

        # Upload to S3/MinIO
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=file_content,
                ContentType=content_type,
            )
            return object_key
        except ClientError as e:
            raise Exception(f"Error uploading file to S3: {e}")

    async def read_file(self, object_key: str) -> bytes:
        """
        Read file from S3/MinIO.

        Args:
            object_key: S3 object key

        Returns:
            File content as bytes
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_key)
            return response["Body"].read()
        except ClientError as e:
            raise Exception(f"Error reading file from S3: {e}")

    async def delete_file(self, object_key: str) -> bool:
        """
        Delete file from S3/MinIO.

        Args:
            object_key: S3 object key

        Returns:
            True if successful
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as e:
            print(f"Error deleting file from S3: {e}")
            return False

    def generate_presigned_url(self, object_key: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for object access.

        Args:
            object_key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_key},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            raise Exception(f"Error generating presigned URL: {e}")

    async def file_exists(self, object_key: str) -> bool:
        """
        Check if file exists in S3/MinIO.

        Args:
            object_key: S3 object key

        Returns:
            True if file exists
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError:
            return False

    def get_file_info(self, object_key: str) -> dict:
        """
        Get file information from S3/MinIO.

        Args:
            object_key: S3 object key

        Returns:
            Dictionary with file metadata
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return {
                "filename": object_key.split("/")[-1],
                "size": response["ContentLength"],
                "modified": response["LastModified"],
                "mimetype": response.get("ContentType", "application/octet-stream"),
                "etag": response["ETag"],
            }
        except ClientError:
            return {}
