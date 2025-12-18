# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Templates management router."""
from pathlib import Path
from typing import List

from ambient_scribe.deps import get_settings, get_templates_dir
from ambient_scribe.models import ErrorResponse, TemplateInfo, TemplateRequest
from ambient_scribe.services.templates import (
    create_template,
    get_available_templates,
    get_template_defaults,
    get_template_info,
    render_template_preview,
)
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

router = APIRouter()


@router.get("/", response_model=List[TemplateInfo])
async def list_templates(
    templates_dir: Path = Depends(get_templates_dir),
) -> List[TemplateInfo]:
    """List all available templates."""
    return get_available_templates(templates_dir)


@router.get("/{template_name}", response_model=TemplateInfo)
async def get_template(
    template_name: str, templates_dir: Path = Depends(get_templates_dir)
) -> TemplateInfo:
    """Get information about a specific template."""
    template_info = get_template_info(template_name, templates_dir)
    if not template_info:
        raise HTTPException(
            status_code=404, detail=f"Template '{template_name}' not found"
        )
    return template_info


@router.post("/", response_model=TemplateInfo)
async def create_new_template(
    request: TemplateRequest, templates_dir: Path = Depends(get_templates_dir)
) -> TemplateInfo:
    """Create a new custom template."""
    try:
        template_info = create_template(request, templates_dir)
        return template_info
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to create template: {str(e)}"
        )


@router.post("/upload")
async def upload_template(
    file: UploadFile = File(...),
    name: str = None,
    templates_dir: Path = Depends(get_templates_dir),
):
    """Upload a template file."""

    # Validate file type
    if not file.filename.endswith(".j2"):
        raise HTTPException(
            status_code=400, detail="Template file must have .j2 extension"
        )

    # Use provided name or derive from filename
    template_name = name or file.filename.replace(".j2", "")

    try:
        # Save template file
        template_path = templates_dir / f"{template_name}.j2"
        with open(template_path, "w") as buffer:
            content = await file.read()
            buffer.write(content.decode("utf-8"))

        return {"message": f"Template '{template_name}' uploaded successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to upload template: {str(e)}"
        )


@router.post("/{template_name}/preview")
async def preview_template(
    template_name: str,
    sample_data: dict = None,
    templates_dir: Path = Depends(get_templates_dir),
):
    """Preview a template with sample data."""

    try:
        # Use sample data or default values

        rendered = render_template_preview(template_name, sample_data, templates_dir)

        return {
            "template_name": template_name,
            "rendered_content": rendered,
            "sample_data": sample_data,
        }

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to preview template: {str(e)}"
        )


@router.get("/{template_name}/defaults", response_model=List[str])
async def get_template_default_messages(
    template_name: str, templates_dir: Path = Depends(get_templates_dir)
) -> List[str]:
    """Get default fallback messages for a specific template."""
    try:
        defaults = get_template_defaults(template_name, templates_dir)
        return defaults
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to get template defaults: {str(e)}"
        )


@router.delete("/{template_name}")
async def delete_template(
    template_name: str, templates_dir: Path = Depends(get_templates_dir)
):
    """Delete a custom template."""

    template_path = templates_dir / f"{template_name}.j2"

    if not template_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Template '{template_name}' not found"
        )

    try:
        template_path.unlink()
        return {"message": f"Template '{template_name}' deleted successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete template: {str(e)}"
        )
