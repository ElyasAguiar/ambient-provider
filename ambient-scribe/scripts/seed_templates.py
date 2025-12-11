#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Seed script to create initial templates for Ambient Scribe
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))


def create_default_templates():
    """Create default template files if they don't exist."""

    templates_dir = PROJECT_ROOT / "apps" / "api" / "templates"
    templates_dir.mkdir(exist_ok=True)

    templates = {
        "soap_default.j2": """{# Template: SOAP Note - Default
# Description: Standard SOAP format for medical documentation
# Sections: subjective, objective, assessment, plan
# Custom: false
#}

# SOAP Note

## Subjective
{{ subjective or "No subjective information documented in the transcript." }}

## Objective
{{ objective or "No objective findings documented in the transcript." }}

## Assessment
{{ assessment or "No assessment provided in the transcript." }}

## Plan
{{ plan or "No treatment plan discussed in the transcript." }}

{% if custom_sections %}
{% for section in custom_sections %}
## {{ section|title }}
{{ get(section.lower()) or "No information provided for this section." }}

{% endfor %}
{% endif %}""",
        "soap_detailed.j2": """{# Template: SOAP Note - Detailed
# Description: Comprehensive SOAP format with additional sections
# Sections: chief_complaint, history_of_present_illness, review_of_systems, past_medical_history, medications, allergies, social_history, assessment, plan, follow_up
# Custom: false
#}

# Detailed SOAP Note

## Chief Complaint
{{ chief_complaint or "Chief complaint not clearly stated in transcript." }}

## History of Present Illness
{{ history_of_present_illness or subjective or "No history of present illness documented." }}

## Review of Systems
{{ review_of_systems or "No review of systems performed." }}

## Past Medical History
{{ past_medical_history or "No past medical history discussed." }}

## Medications
{{ medications or "No medications discussed." }}

## Allergies
{{ allergies or "No allergies mentioned." }}

## Social History
{{ social_history or "No social history obtained." }}

## Assessment
{{ assessment or "No clinical assessment provided." }}

## Plan
{{ plan or "No treatment plan discussed." }}

## Follow-up
{{ follow_up or "No follow-up plans specified." }}

{% if additional_notes %}
## Additional Notes
{{ additional_notes }}
{% endif %}""",
        "progress_note.j2": """{# Template: Progress Note
# Description: Follow-up progress note format
# Sections: interval_history, current_symptoms, examination_findings, assessment, plan, medication_changes, follow_up, patient_education
# Custom: false
#}

# Progress Note

## Interval History
{{ interval_history or subjective or "No interval history since last visit documented." }}

## Current Symptoms
{{ current_symptoms or "No current symptoms discussed." }}

## Examination Findings
{{ examination_findings or "No examination findings documented." }}

## Assessment
{{ assessment or "No assessment provided for this visit." }}

## Plan
{{ plan or "No plan discussed for ongoing care." }}

## Medication Changes
{{ medication_changes or "No medication changes discussed." }}

## Follow Up
{{ follow_up or "No specific follow-up instructions provided." }}

## Patient Education
{{ patient_education or "No patient education documented." }}""",
        "custom_example.j2": """{# Template: Custom Medical Note
# Description: Custom template with alternative section naming
# Sections: chief_complaint, history, examination, clinical_impression, treatment_plan
# Custom: true
#}

# Custom Medical Note

## Chief Complaint
{{ chief_complaint or "Not documented" }}

## History
{{ history or "No history obtained" }}

## Examination
{{ examination or "No examination performed" }}

## Clinical Impression
{{ clinical_impression or "No impression documented" }}

## Treatment Plan
{{ treatment_plan or "No plan discussed" }}

{% if custom_sections %}
{% for section in custom_sections %}
## {{ section|title }}
{{ get(section.lower()) or "No information provided" }}

{% endfor %}
{% endif %}""",
    }

    created_count = 0
    for filename, content in templates.items():
        template_path = templates_dir / filename

        if not template_path.exists():
            with open(template_path, "w") as f:
                f.write(content)
            print(f"Created template: {filename}")
            created_count += 1
        else:
            print(f"Template already exists: {filename}")

    return created_count


def create_sample_data():
    """Create sample data files for testing."""

    sample_dir = PROJECT_ROOT / "sample_data"
    sample_dir.mkdir(exist_ok=True)

    # Create a sample transcript JSON
    sample_transcript = {
        "id": "sample-001",
        "segments": [
            {
                "start": 0.0,
                "end": 15.0,
                "text": "Good morning, how are you feeling today?",
                "speaker_tag": 1,
                "confidence": 0.95,
            },
            {
                "start": 15.5,
                "end": 32.0,
                "text": "I've been having some chest pain and shortness of breath for the past few days.",
                "speaker_tag": 2,
                "confidence": 0.92,
            },
            {
                "start": 33.0,
                "end": 48.0,
                "text": "Can you describe the chest pain? Is it sharp, dull, or crushing?",
                "speaker_tag": 1,
                "confidence": 0.97,
            },
        ],
        "language": "en-US",
        "duration": 180.0,
        "filename": "sample_visit.mp3",
        "created_at": "2024-01-01T10:00:00Z",
    }

    import json

    sample_file = sample_dir / "sample_transcript.json"
    if not sample_file.exists():
        with open(sample_file, "w") as f:
            json.dump(sample_transcript, f, indent=2)
        print(f"Created sample transcript: {sample_file}")
    else:
        print(f"Sample transcript already exists")


def main():
    """Main seeding function."""
    print("Seeding Ambient Scribe Templates and Sample Data")
    print("=" * 50)

    try:
        # Create templates
        created_templates = create_default_templates()

        # Create sample data
        create_sample_data()

        print(f"\nSeeding completed successfully!")
        print(f"Created {created_templates} new templates")
        print(f"Templates directory: {PROJECT_ROOT / 'templates'}")
        print(f"Sample data directory: {PROJECT_ROOT / 'sample_data'}")

    except Exception as e:
        print(f"\nError during seeding: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
