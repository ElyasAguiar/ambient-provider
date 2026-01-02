# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local file storage manager."""
import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os


class StorageManager:
    """Manages local file storage operations."""

    def __init__(self, base_path: str = "./uploads"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_file(
        self, file_content: bytes, filename: str, subfolder: Optional[str] = None
    ) -> str:
        """Save file content and return the file path."""

        # Generate unique filename
        file_id = str(uuid.uuid4())
        file_extension = Path(filename).suffix
        unique_filename = f"{file_id}{file_extension}"

        # Determine save path
        if subfolder:
            save_dir = self.base_path / subfolder
            save_dir.mkdir(parents=True, exist_ok=True)
            file_path = save_dir / unique_filename
        else:
            file_path = self.base_path / unique_filename

        # Save file
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path)

    async def read_file(self, file_path: str) -> bytes:
        """Read file content."""
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def delete_file(self, file_path: str) -> bool:
        """Delete a file."""
        try:
            await aiofiles.os.remove(file_path)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        return Path(file_path).exists()

    def get_file_info(self, file_path: str) -> dict:
        """Get file information."""
        path = Path(file_path)

        if not path.exists():
            return {}

        stat = path.stat()

        return {
            "filename": path.name,
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "mimetype": mimetypes.guess_type(str(path))[0],
        }

    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file."""
        path = Path(file_path)

        if not path.exists():
            return ""

        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()
