# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Guardrails service for medical privacy protection."""
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ambient_scribe.deps import Settings
from nemoguardrails import LLMRails, RailsConfig

logger = logging.getLogger(__name__)


class MedicalGuardrailsService:
    """Service for applying NeMo Guardrails to protect patient information in medical content."""

    def __init__(self, settings: Settings):
        """Initialize the guardrails service with configuration."""
        self.settings = settings
        self._rails: Optional[LLMRails] = None
        self._config_path = Path(settings.guardrails_config_path)

    async def initialize(self) -> None:
        """Initialize the NeMo Guardrails configuration."""
        try:
            if not self._config_path.exists():
                raise FileNotFoundError(
                    f"Guardrails config directory not found: {self._config_path}"
                )

            logger.info(f"Loading guardrails config from: {self._config_path}")

            # Load the rails configuration
            config = RailsConfig.from_path(str(self._config_path))

            # Override model configuration with current settings
            if config.models:
                for model_config in config.models:
                    if model_config.type == "main":
                        # Update with current API settings
                        model_config.engine = "nvidia_ai_endpoints"
                        model_config.model = self.settings.llm_model

                        # Set API configuration
                        if not hasattr(model_config, "parameters"):
                            model_config.parameters = {}

                        model_config.parameters.update(
                            {
                                "api_key": self.settings.nvidia_api_key,
                                "base_url": self.settings.openai_base_url,
                                "temperature": 0.1,
                                "max_tokens": 1024,
                            }
                        )

            # Initialize the rails with the configuration
            self._rails = LLMRails(config)

            logger.info("Guardrails service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize guardrails service: {str(e)}")
            raise

    async def filter_input(self, text: str) -> str:
        """
        Apply input guardrails to filter sensitive patient information.

        Args:
            text: Input text to filter

        Returns:
            Filtered text with sensitive information masked
        """
        if not self._rails:
            await self.initialize()

        try:
            # Apply input guardrails
            result = await self._rails.generate_async(
                messages=[
                    {
                        "role": "user",
                        "content": f"Apply input privacy protection to this medical transcript: {text}",
                    }
                ]
            )

            # Extract the filtered content
            if result and "content" in result:
                filtered_text = result["content"]

                # Log if sensitive information was detected and masked
                if filtered_text != text:
                    logger.info(
                        "Input filtering applied: sensitive information detected and masked"
                    )

                return filtered_text

            return text

        except Exception as e:
            logger.warning(f"Input filtering failed, using original text: {str(e)}")
            return text

    async def filter_output(self, text: str) -> str:
        """
        Apply output guardrails to ensure no sensitive patient information is in the response.

        Args:
            text: Output text to filter

        Returns:
            Filtered text with any remaining sensitive information masked
        """
        if not self._rails:
            await self.initialize()

        try:
            # Apply output guardrails
            result = await self._rails.generate_async(
                messages=[
                    {
                        "role": "user",
                        "content": f"Apply output privacy protection to this medical note: {text}",
                    }
                ]
            )

            # Extract the filtered content
            if result and "content" in result:
                filtered_text = result["content"]

                # Log if sensitive information was detected and masked
                if filtered_text != text:
                    logger.info(
                        "Output filtering applied: sensitive information detected and masked"
                    )

                return filtered_text

            return text

        except Exception as e:
            logger.warning(f"Output filtering failed, using original text: {str(e)}")
            return text

    async def validate_content(self, text: str) -> Dict[str, Any]:
        """
        Validate content for privacy compliance and return detailed analysis.

        Args:
            text: Text to validate

        Returns:
            Dictionary with validation results
        """
        if not self._rails:
            await self.initialize()

        try:
            # Check for potential privacy violations
            violations = []

            # Simple pattern-based checks as fallback
            privacy_patterns = [
                (r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", "POTENTIAL_NAME"),
                (r"\b\d{3}-\d{2}-\d{4}\b", "SSN_PATTERN"),
                (r"\b\d{3}-\d{3}-\d{4}\b", "PHONE_PATTERN"),
                (
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                    "EMAIL_PATTERN",
                ),
                (r"\bMRN[:\s]*[A-Za-z0-9-]+\b", "MRN_PATTERN"),
            ]

            import re

            for pattern, violation_type in privacy_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    violations.append(violation_type)

            return {
                "is_compliant": len(violations) == 0,
                "violations": violations,
                "text_length": len(text),
                "message": (
                    "Content validated for privacy compliance"
                    if len(violations) == 0
                    else f"Found {len(violations)} potential privacy violations"
                ),
            }

        except Exception as e:
            logger.error(f"Content validation failed: {str(e)}")
            return {
                "is_compliant": False,
                "violations": ["VALIDATION_ERROR"],
                "text_length": len(text),
                "message": f"Validation error: {str(e)}",
            }

    def is_available(self) -> bool:
        """Check if the guardrails service is available and configured."""
        return (
            self._config_path.exists()
            and (self._config_path / "config.yml").exists()
            and (self._config_path / "prompts.yml").exists()
        )


# Global instance for dependency injection
_guardrails_service: Optional[MedicalGuardrailsService] = None


async def get_guardrails_service(settings: Settings) -> MedicalGuardrailsService:
    """Get or create the global guardrails service instance."""
    global _guardrails_service

    if _guardrails_service is None:
        _guardrails_service = MedicalGuardrailsService(settings)
        await _guardrails_service.initialize()

    return _guardrails_service


async def apply_input_guardrails(text: str, settings: Settings) -> str:
    """Convenience function to apply input guardrails."""
    service = await get_guardrails_service(settings)
    return await service.filter_input(text)


async def apply_output_guardrails(text: str, settings: Settings) -> str:
    """Convenience function to apply output guardrails."""
    service = await get_guardrails_service(settings)
    return await service.filter_output(text)


async def validate_privacy_compliance(text: str, settings: Settings) -> Dict[str, Any]:
    """Convenience function to validate content for privacy compliance."""
    service = await get_guardrails_service(settings)
    return await service.validate_content(text)
