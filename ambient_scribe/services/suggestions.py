# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Autocomplete suggestions service for note editing."""
import re
from typing import List, Optional, Set

try:
    from openai import AsyncOpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from ambient_scribe.deps import Settings
from ambient_scribe.models import Transcript

# Medical terminology and common phrases for autocomplete
MEDICAL_TERMS = {
    # Body systems and anatomy
    "cardiovascular",
    "respiratory",
    "gastrointestinal",
    "neurological",
    "musculoskeletal",
    "endocrine",
    "genitourinary",
    "dermatological",
    "psychiatric",
    "ophthalmologic",
    "otolaryngologic",
    "hematologic",
    "immunologic",
    "rheumatologic",
    # Common symptoms
    "chest pain",
    "shortness of breath",
    "abdominal pain",
    "headache",
    "nausea",
    "vomiting",
    "diarrhea",
    "constipation",
    "fatigue",
    "dizziness",
    "palpitations",
    "syncope",
    "fever",
    "chills",
    "night sweats",
    "weight loss",
    "weight gain",
    "appetite",
    "dyspnea",
    "orthopnea",
    "paroxysmal nocturnal dyspnea",
    "edema",
    "claudication",
    # Physical exam findings
    "heart rate",
    "blood pressure",
    "respiratory rate",
    "temperature",
    "oxygen saturation",
    "alert and oriented",
    "no acute distress",
    "well-appearing",
    "ill-appearing",
    "afebrile",
    "normocephalic",
    "atraumatic",
    "pupils equal round reactive to light",
    "extraocular muscles intact",
    "conjunctiva",
    "sclera",
    "mucous membranes",
    "neck supple",
    "no lymphadenopathy",
    "thyroid",
    "jugular venous distension",
    "carotid bruits",
    "heart sounds",
    "murmur",
    "gallop",
    "rub",
    "lungs clear",
    "wheezes",
    "rales",
    "rhonchi",
    "decreased breath sounds",
    "dullness to percussion",
    "abdomen soft",
    "non-tender",
    "non-distended",
    "bowel sounds",
    "hepatomegaly",
    "splenomegaly",
    "rebound tenderness",
    "guarding",
    "extremities",
    "pulses",
    "capillary refill",
    "cyanosis",
    "clubbing",
    "edema",
    "range of motion",
    "motor strength",
    "sensation",
    "reflexes",
    "coordination",
    "gait",
    # Common diagnoses
    "hypertension",
    "diabetes mellitus",
    "hyperlipidemia",
    "coronary artery disease",
    "congestive heart failure",
    "atrial fibrillation",
    "myocardial infarction",
    "pneumonia",
    "chronic obstructive pulmonary disease",
    "asthma",
    "bronchitis",
    "gastroesophageal reflux disease",
    "peptic ulcer disease",
    "inflammatory bowel disease",
    "urinary tract infection",
    "kidney stones",
    "chronic kidney disease",
    "depression",
    "anxiety",
    "bipolar disorder",
    "schizophrenia",
    "dementia",
    "stroke",
    "transient ischemic attack",
    "seizure disorder",
    "migraine",
    "osteoarthritis",
    "rheumatoid arthritis",
    "fibromyalgia",
    "osteoporosis",
    "hypothyroidism",
    "hyperthyroidism",
    "diabetes type 1",
    "diabetes type 2",
    # Medications
    "aspirin",
    "acetaminophen",
    "ibuprofen",
    "lisinopril",
    "metoprolol",
    "amlodipine",
    "atorvastatin",
    "simvastatin",
    "metformin",
    "insulin",
    "levothyroxine",
    "omeprazole",
    "pantoprazole",
    "albuterol",
    "fluticasone",
    "prednisone",
    "warfarin",
    "apixaban",
    "clopidogrel",
    "furosemide",
    "hydrochlorothiazide",
    # SOAP note sections
    "chief complaint",
    "history of present illness",
    "review of systems",
    "past medical history",
    "past surgical history",
    "medications",
    "allergies",
    "social history",
    "family history",
    "physical examination",
    "assessment",
    "plan",
    "vital signs",
    "general appearance",
    "differential diagnosis",
    # Common phrases
    "patient reports",
    "patient denies",
    "patient states",
    "patient complains of",
    "on examination",
    "physical exam reveals",
    "assessment and plan",
    "will continue",
    "will start",
    "will discontinue",
    "follow up",
    "return to clinic",
    "if symptoms worsen",
    "as needed",
    "monitor closely",
    "patient education provided",
    "patient counseled on",
    "discussed with patient",
}

# Convert to lowercase for matching
MEDICAL_TERMS = {term.lower() for term in MEDICAL_TERMS}


async def get_autocomplete_suggestions(
    prefix: str,
    transcript: Optional[Transcript] = None,
    context: Optional[str] = None,
    settings: Settings = None,
    max_suggestions: int = 10,
) -> List[str]:
    """
    Generate autocomplete suggestions for the given prefix.

    Args:
        prefix: The text prefix to complete
        transcript: Optional transcript for context-aware suggestions
        context: Optional surrounding text context
        settings: Application settings
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of suggestion strings
    """
    suggestions = []
    prefix_lower = prefix.lower().strip()

    if not prefix_lower or len(prefix_lower) < 2:
        return []

    # 1. Medical terminology matching
    medical_matches = _get_medical_term_suggestions(prefix_lower, max_suggestions // 3)
    suggestions.extend(medical_matches)

    # 2. Transcript-based suggestions (if available)
    if transcript:
        transcript_matches = _get_transcript_based_suggestions(
            prefix_lower, transcript, max_suggestions // 3
        )
        suggestions.extend(transcript_matches)

    # 3. Context-aware suggestions (if available)
    if context:
        context_matches = _get_context_based_suggestions(
            prefix_lower, context, max_suggestions // 3
        )
        suggestions.extend(context_matches)

    # 4. AI-powered suggestions (if NVIDIA API is available)
    if settings and settings.nvidia_api_key and len(suggestions) < max_suggestions:
        try:
            ai_matches = await _get_ai_powered_suggestions(
                prefix,
                context,
                transcript,
                settings,
                max_suggestions - len(suggestions),
            )
            suggestions.extend(ai_matches)
        except Exception as e:
            print(f"AI suggestions failed: {e}")

    # Remove duplicates while preserving order
    seen = set()
    unique_suggestions = []
    for suggestion in suggestions:
        if suggestion.lower() not in seen:
            seen.add(suggestion.lower())
            unique_suggestions.append(suggestion)

    return unique_suggestions[:max_suggestions]


def _get_medical_term_suggestions(prefix: str, max_suggestions: int) -> List[str]:
    """Get suggestions from medical terminology."""
    suggestions = []

    # Direct prefix matches
    for term in MEDICAL_TERMS:
        if term.startswith(prefix):
            suggestions.append(term.title())
            if len(suggestions) >= max_suggestions:
                break

    # Fuzzy matches (word boundaries)
    if len(suggestions) < max_suggestions:
        for term in MEDICAL_TERMS:
            if len(suggestions) >= max_suggestions:
                break

            # Check if any word in the term starts with the prefix
            words = term.split()
            for word in words:
                if word.startswith(prefix) and term.title() not in suggestions:
                    suggestions.append(term.title())
                    break

    return suggestions


def _get_transcript_based_suggestions(
    prefix: str, transcript: Transcript, max_suggestions: int
) -> List[str]:
    """Get suggestions based on transcript content."""
    suggestions = []

    if not transcript.segments:
        return suggestions

    # Extract words and phrases from transcript
    all_text = " ".join(segment.text for segment in transcript.segments)

    # Find words/phrases that start with the prefix
    words = re.findall(r"\b\w+", all_text.lower())
    phrases = _extract_phrases(all_text.lower())

    # Word matches
    for word in set(words):
        if word.startswith(prefix) and len(word) > len(prefix):
            suggestions.append(word.title())
            if len(suggestions) >= max_suggestions // 2:
                break

    # Phrase matches
    for phrase in set(phrases):
        if phrase.startswith(prefix) and len(phrase) > len(prefix):
            suggestions.append(phrase.title())
            if len(suggestions) >= max_suggestions:
                break

    return suggestions[:max_suggestions]


def _get_context_based_suggestions(prefix: str, context: str, max_suggestions: int) -> List[str]:
    """Get suggestions based on surrounding context."""
    suggestions = []

    # Extract words from context
    words = re.findall(r"\b\w+", context.lower())
    phrases = _extract_phrases(context.lower())

    # Find relevant completions based on context
    for word in set(words):
        if word.startswith(prefix) and len(word) > len(prefix):
            suggestions.append(word.title())
            if len(suggestions) >= max_suggestions // 2:
                break

    for phrase in set(phrases):
        if phrase.startswith(prefix) and len(phrase) > len(prefix):
            suggestions.append(phrase.title())
            if len(suggestions) >= max_suggestions:
                break

    return suggestions[:max_suggestions]


async def _get_ai_powered_suggestions(
    prefix: str,
    context: Optional[str],
    transcript: Optional[Transcript],
    settings: Settings,
    max_suggestions: int,
) -> List[str]:
    """Get AI-powered suggestions using NVIDIA API."""
    if not HAS_OPENAI:
        return []

    client = AsyncOpenAI(api_key=settings.nvidia_api_key, base_url=settings.openai_base_url)

    # Build prompt for AI suggestions
    prompt_parts = [
        f"Complete the medical note text that starts with: '{prefix}'",
        "Provide 3-5 medically appropriate completions.",
        "Focus on common medical terminology and phrases.",
        "Return only the completion text, one per line.",
    ]

    if context:
        prompt_parts.insert(1, f"Context: {context[-200:]}")  # Last 200 chars of context

    if transcript:
        # Include relevant transcript excerpts
        transcript_text = " ".join(segment.text for segment in transcript.segments[:5])
        prompt_parts.insert(-2, f"Patient discussion excerpt: {transcript_text[:300]}")

    prompt = "\n".join(prompt_parts)

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical assistant helping with clinical note completion.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
            temperature=0.3,
        )

        if response.choices and response.choices[0].message.content:
            # Parse the response into individual suggestions
            suggestions = []
            lines = response.choices[0].message.content.strip().split("\n")

            for line in lines:
                line = line.strip()
                if line and not line.startswith("-") and not line.startswith("*"):
                    # Remove numbering if present
                    line = re.sub(r"^\d+\.\s*", "", line)
                    if line.lower().startswith(prefix.lower()):
                        suggestions.append(line)

            return suggestions[:max_suggestions]

    except Exception as e:
        print(f"AI suggestion error: {e}")
        return []

    return []


def _extract_phrases(text: str, max_words: int = 4) -> List[str]:
    """Extract meaningful phrases from text."""
    phrases = []
    words = text.split()

    # Extract phrases of 2-4 words
    for i in range(len(words)):
        for length in range(2, min(max_words + 1, len(words) - i + 1)):
            phrase = " ".join(words[i : i + length])
            if len(phrase) > 5:  # Minimum phrase length
                phrases.append(phrase)

    return phrases
