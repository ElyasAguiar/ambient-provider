# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schemas for templates domain."""
from typing import List

from pydantic import BaseModel, Field


class TemplateInfo(BaseModel):
    """Template metadata."""

    name: str = Field(..., description="Template name")
    display_name: str = Field(..., description="Human-readable template name")
    description: str = Field(..., description="Template description")
    sections: List[str] = Field(..., description="Available sections")
    is_custom: bool = Field(default=False, description="Whether this is a custom template")


class TemplateRequest(BaseModel):
    """Request to create or update a template."""

    name: str = Field(..., description="Template name")
    display_name: str = Field(..., description="Human-readable template name")
    description: str = Field(..., description="Template description")
    template_content: str = Field(..., description="Jinja2 template content")
    sections: List[str] = Field(..., description="Available sections")
