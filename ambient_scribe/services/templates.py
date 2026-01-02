# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Template management service using Jinja2."""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from ambient_scribe.models import TemplateInfo, TemplateRequest


def extract_template_defaults(template_content: str) -> List[str]:
    """Extract default fallback messages from a Jinja2 template.

    Parses expressions like {{ variable or "default message" }} and extracts the default messages.
    """
    defaults = []

    # Pattern to match Jinja2 expressions with 'or' fallbacks
    # Matches: {{ variable or "default message" }} or {{ var1 or var2 or "default" }}
    pattern = r'\{\{\s*[^}]+?\s+or\s+"([^"]+)"\s*\}\}'

    matches = re.findall(pattern, template_content)
    defaults.extend(matches)

    # Also handle single quotes
    pattern_single = r"\{\{\s*[^}]+?\s+or\s+'([^']+)'\s*\}\}"
    matches_single = re.findall(pattern_single, template_content)
    defaults.extend(matches_single)

    return defaults


def get_template_defaults(template_name: str, templates_dir: Path) -> List[str]:
    """Get default messages for a specific template by name."""
    try:
        template_path = templates_dir / f"{template_name}.j2"
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            return extract_template_defaults(content)
        else:
            # Fallback to built-in templates
            builtin = get_builtin_templates()
            if template_name in builtin:
                return extract_template_defaults(builtin[template_name])
    except Exception as e:
        print(f"Error extracting defaults for template {template_name}: {e}")

    return []


def get_available_templates(templates_dir: Path) -> List[TemplateInfo]:
    """Get list of all available templates, including built-ins and filesystem templates."""

    templates: List[TemplateInfo] = []

    # Include filesystem templates if directory exists
    if templates_dir.exists():
        for template_file in templates_dir.glob("*.j2"):
            try:
                template_info = get_template_info(template_file.stem, templates_dir)
                if template_info:
                    templates.append(template_info)
            except Exception:
                continue  # Skip invalid templates

    # Include built-in templates (ensure no duplicates by name)
    builtin = get_builtin_templates()
    for name, content in builtin.items():
        if any(t.name == name for t in templates):
            continue
        sections = detect_template_sections(content)
        templates.append(
            TemplateInfo(
                name=name,
                display_name=name.replace("_", " ").title(),
                description=f"{name} template",
                sections=sections,
                is_custom=False,
            )
        )

    return templates


def get_template_info(template_name: str, templates_dir: Path) -> Optional[TemplateInfo]:
    """Get information about a specific template. Falls back to built-ins if no file exists."""

    template_path = templates_dir / f"{template_name}.j2"

    # Prefer filesystem template if present
    if template_path.exists():
        try:
            with open(template_path, "r") as f:
                content = f.read()

            metadata = extract_template_metadata(content)
            sections = detect_template_sections(content)

            return TemplateInfo(
                name=template_name,
                display_name=metadata.get("display_name", template_name.replace("_", " ").title()),
                description=metadata.get("description", f"{template_name} template"),
                sections=sections,
                is_custom=metadata.get("is_custom", False),
            )
        except Exception:
            return None

    # Fallback to built-in template registry
    builtin = get_builtin_templates()
    if template_name in builtin:
        content = builtin[template_name]
        sections = detect_template_sections(content)
        return TemplateInfo(
            name=template_name,
            display_name=template_name.replace("_", " ").title(),
            description=f"{template_name} template",
            sections=sections,
            is_custom=False,
        )

    return None


def create_template(request: TemplateRequest, templates_dir: Path) -> TemplateInfo:
    """Create a new template."""

    # Ensure templates directory exists
    templates_dir.mkdir(parents=True, exist_ok=True)

    # Validate template name
    if not re.match(r"^[a-zA-Z0-9_-]+$", request.name):
        raise ValueError(
            "Template name can only contain letters, numbers, hyphens, and underscores"
        )

    template_path = templates_dir / f"{request.name}.j2"

    # Add metadata header to template
    template_content = f"""{{# Template: {request.display_name}
# Description: {request.description}
# Sections: {', '.join(request.sections)}
# Custom: true
#}}

{request.template_content}
"""

    try:
        # Validate Jinja2 syntax
        env = Environment()
        env.parse(template_content)

        # Write template file
        with open(template_path, "w") as f:
            f.write(template_content)

        return TemplateInfo(
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            sections=request.sections,
            is_custom=True,
        )

    except Exception as e:
        raise ValueError(f"Invalid template syntax: {str(e)}")


def render_template(template_name: str, **kwargs) -> str:
    """Render a template with the provided data.

    Tries filesystem templates first; if not found, falls back to built-in registry.
    """

    # Get templates directory
    from ambient_scribe.deps import get_templates_dir

    templates_dir = get_templates_dir()

    try:
        # Set up Jinja2 environment for filesystem templates
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,  # Medical notes are plain text/markdown
            trim_blocks=False,  # Preserve exact formatting
            lstrip_blocks=False,  # Preserve exact formatting
        )

        template = env.get_template(f"{template_name}.j2")
        rendered = template.render(**kwargs)
        return rendered

    except TemplateNotFound:
        # Fallback to built-in templates
        builtin = get_builtin_templates()
        if template_name not in builtin:
            raise ValueError(f"Template '{template_name}' not found")
        try:
            env = Environment(autoescape=False, trim_blocks=False, lstrip_blocks=False)
            template = env.from_string(builtin[template_name])
            rendered = template.render(**kwargs)
            return rendered
        except Exception as e:
            raise ValueError(f"Template rendering failed: {str(e)}")
    except Exception as e:
        raise ValueError(f"Template rendering failed: {str(e)}")


def render_template_preview(
    template_name: str, sample_data: Dict[str, Any], templates_dir: Path
) -> str:
    """Render a template with sample data for preview. Supports built-ins as fallback."""

    try:
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
            trim_blocks=False,
            lstrip_blocks=False,
        )
        template = env.get_template(f"{template_name}.j2")
        rendered = template.render(**sample_data)
        return rendered
    except TemplateNotFound:
        # Fallback to built-in templates
        builtin = get_builtin_templates()
        if template_name not in builtin:
            raise ValueError(f"Preview rendering failed: Template '{template_name}' not found")
        env = Environment(autoescape=False)
        template = env.from_string(builtin[template_name])
        rendered = template.render(**sample_data)
        return rendered.strip()
    except Exception as e:
        raise ValueError(f"Preview rendering failed: {str(e)}")


def extract_template_metadata(content: str) -> Dict[str, Any]:
    """Extract metadata from template comments."""

    metadata = {}

    # Look for metadata in template comments
    comment_pattern = r"\{\#\s*(.*?)\s*\#\}"
    matches = re.findall(comment_pattern, content, re.DOTALL)

    for match in matches:
        lines = match.strip().split("\n")
        for line in lines:
            line = line.strip()
            if ":" in line and line.startswith("#"):
                key, value = line[1:].split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()

                # Convert boolean strings
                if value.lower() in ["true", "false"]:
                    value = value.lower() == "true"

                metadata[key] = value

    return metadata


def detect_template_sections(content: str) -> List[str]:
    """Detect sections in a template by analyzing metadata and variable usage."""

    # First, try to get sections from template metadata
    metadata = extract_template_metadata(content)
    if "sections" in metadata:
        sections_str = metadata["sections"]
        if isinstance(sections_str, str):
            # Parse comma-separated sections
            sections = [s.strip() for s in sections_str.split(",") if s.strip()]
            if sections:
                return sections

    # Fallback: detect sections from template content
    sections = []

    # Look for common section variables
    common_sections = [
        "subjective",
        "objective",
        "assessment",
        "plan",
        "chief_complaint",
        "history",
        "exam",
        "diagnosis",
        "medications",
        "allergies",
        "vital_signs",
        "social_history",
        "family_history",
        "review_of_systems",
        "interval_history",
        "current_symptoms",
        "follow_up",
        "history_present_illness",
        "past_medical_history",
        "medication_changes",
        "patient_education",
        "examination_findings",
    ]

    content_lower = content.lower()

    for section in common_sections:
        # Look for {{ section }} or {{ section or ... }} patterns
        if f"{{{{{section}" in content_lower or f"# {section}" in content_lower:
            sections.append(section)

    # Also look for custom variables
    variable_pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)"
    variables = re.findall(variable_pattern, content)

    for var in variables:
        if var.lower() not in sections and var.lower() not in common_sections:
            sections.append(var.lower())

    return sections


# Built-in template registry
def get_builtin_templates() -> Dict[str, str]:
    """Get built-in template definitions."""

    return {
        "soap_default": """# SOAP Note

## Subjective
{{ subjective or 'No subjective information documented.' }}

## Objective
{{ objective or 'No objective information documented.' }}

## Assessment
{{ assessment or 'No assessment documented.' }}

## Plan
{{ plan or 'No plan documented.' }}
""",
        "soap_detailed": """# Detailed SOAP Note

## Chief Complaint
{{ chief_complaint or 'Not documented' }}

## History of Present Illness
{{ subjective or 'No HPI documented.' }}

## Physical Examination
{{ objective or 'No physical exam documented.' }}

## Assessment and Plan
### Assessment
{{ assessment or 'No assessment documented.' }}

### Plan
{{ plan or 'No plan documented.' }}

## Additional Notes
{{ additional_notes or 'No additional notes.' }}
""",
        "progress_note": """# Progress Note

**Date:** {{ date or 'Not specified' }}
**Provider:** {{ provider or 'Not specified' }}

## Interval History
{{ subjective or 'No interval history documented.' }}

## Examination
{{ objective or 'No examination findings documented.' }}

## Assessment
{{ assessment or 'No assessment documented.' }}

## Plan
{{ plan or 'No plan documented.' }}

## Follow Up
{{ follow_up or 'No follow-up specified.' }}
""",
    }
