# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""User SQLAlchemy model."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ambient_scribe.database import Base


class User(Base):
    """User model for authentication and multi-tenancy."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    workspaces: Mapped[list["Workspace"]] = relationship(
        "Workspace", back_populates="owner", cascade="all, delete-orphan"
    )
    contexts: Mapped[list["Context"]] = relationship(
        "Context", back_populates="owner", cascade="all, delete-orphan"
    )
    templates: Mapped[list["Template"]] = relationship(
        "Template", back_populates="created_by_user", cascade="all, delete-orphan"
    )
    ratings: Mapped[list["ContextRating"]] = relationship(
        "ContextRating", back_populates="user", cascade="all, delete-orphan"
    )
