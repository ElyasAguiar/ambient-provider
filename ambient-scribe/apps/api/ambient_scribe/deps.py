# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies and dependency injection."""
import os
from functools import lru_cache
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings."""

    # API Configuration
    debug: bool = False
    api_title: str = "Ambient Scribe API"
    api_version: str = "0.1.0"

    # NVIDIA API
    self_hosted: bool = True
    riva_function_id: str = ""
    nvidia_api_key: str = ""
    openai_base_url: str = (
        "http://llama-nim:8000/v1"  # Default to self-hosted LLM NIM "https://integrate.api.nvidia.com/v1"
    )
    llm_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1"

    # Riva ASR Configuration
    riva_uri: str = "parakeet-nim:50051"
    riva_model: str = "parakeet-1.1b-en-US-asr-offline-silero-vad-sortformer"
    riva_language: str = "en-US"
    enable_speaker_diarization: bool = True

    # Streaming Configuration
    enable_streaming: bool = True
    streaming_chunk_size: int = 1600

    # Storage
    storage_backend: str = "local"  # "local"
    upload_dir: str = "./uploads"
    max_file_size: int = 100 * 1024 * 1024  # 100MB

    # Templates
    templates_dir: str = "./templates"

    # Processing
    max_concurrent_transcriptions: int = 3
    transcription_timeout: int = 300  # 5 minutes

    # Guardrails Configuration
    enable_guardrails: bool = False
    guardrails_config_path: str = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config"
    )
    guardrails_log_level: str = "INFO"

    # System Prompt Configuration
    system_prompt: str = (
        "You are a medical professional creating clinical notes. Be concise and accurate."
    )

    class Config:
        env_file = ".env"
        case_sensitive = False


def _load_settings() -> Settings:
    """Internal function to load settings."""
    # Always load .env file, but only override in development for hot-reloading
    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    load_dotenv(override=debug_mode)  # Always load, but only override in debug mode

    settings = Settings()

    # Optional: Print what values were loaded (for debugging)
    print("Settings loaded:")
    print(f"  nvidia_api_key: {'***' if settings.nvidia_api_key else 'NOT SET'}")
    print(f"  debug: {settings.debug}")
    print(f"  riva_uri: {settings.riva_uri}")
    print(f"  enable_streaming: {settings.enable_streaming}")

    return settings


# Cached version for production
@lru_cache()
def _get_settings_cached() -> Settings:
    """Get cached application settings for production."""
    return _load_settings()


def get_settings() -> Settings:
    """Get application settings with smart caching based on environment."""
    # In development (DEBUG=true), don't cache settings to allow hot-reloading
    # In production (DEBUG=false), use caching for performance
    if os.getenv("DEBUG", "false").lower() == "true":
        return _load_settings()  # No caching in development
    else:
        return _get_settings_cached()  # Cached in production


def get_upload_dir() -> Path:
    """Get upload directory path."""
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_templates_dir() -> Path:
    """Get templates directory path."""
    settings = get_settings()
    templates_dir = Path(settings.templates_dir)
    if not templates_dir.exists():
        # Create templates dir and look for templates in parent directories
        templates_dir.mkdir(parents=True, exist_ok=True)
        # Check if we're in the nested structure and find the root templates
        current = Path.cwd()
        for parent in [current, *current.parents]:
            potential_templates = parent / "templates"
            if potential_templates.exists() and potential_templates.is_dir():
                return potential_templates
    return templates_dir
