"""NouGen Voice & Brand Pronunciation Adapter.

Implements the canonical brand/voice pronunciation decision (Source shard 28144@db4):
- 'Nou Gen AI' with 'gen' as Haitian Creole 'gen' = 'have' (audible beat: Nou. Gen. A-I.).
- 'Nou. Gen. A-I.' carries the Haitian Creole meaning 'We have AI'.
- Eliminates anglicized 'jen' or 'generation' default pronunciations across TTS/Persona adapters.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Dict, Any

CANONICAL_BRAND_TEXT = "Nou Gen AI"
HAITIAN_CREOLE_GEN_IPA = "ɡɛ̃"
HAITIAN_CREOLE_NOU_IPA = "nu"
HAITIAN_CREOLE_AI_IPA = "eɪ.aɪ"

# Full canonical brand phonetic representations
CANONICAL_IPA = f"{HAITIAN_CREOLE_NOU_IPA} {HAITIAN_CREOLE_GEN_IPA} {HAITIAN_CREOLE_AI_IPA}"
CANONICAL_SSML = (
    '<phoneme alphabet="ipa" ph="nu">Nou</phoneme> '
    '<phoneme alphabet="ipa" ph="ɡɛ̃">Gen</phoneme> '
    '<phoneme alphabet="ipa" ph="eɪ.aɪ">AI</phoneme>'
)
CANONICAL_BEAT_DELIVERY = "Nou. Gen. A-I."


@dataclass(frozen=True)
class PronunciationOverride:
    token: str
    target_ipa: str
    ssml_override: str
    phonetic_respelling: str
    meaning: str


BRAND_OVERRIDES: Dict[str, PronunciationOverride] = {
    "nou": PronunciationOverride(
        token="Nou",
        target_ipa=HAITIAN_CREOLE_NOU_IPA,
        ssml_override='<phoneme alphabet="ipa" ph="nu">Nou</phoneme>',
        phonetic_respelling="Noo",
        meaning="We / Us (Haitian Creole)"
    ),
    "gen": PronunciationOverride(
        token="Gen",
        target_ipa=HAITIAN_CREOLE_GEN_IPA,
        ssml_override='<phoneme alphabet="ipa" ph="ɡɛ̃">Gen</phoneme>',
        phonetic_respelling="Gẽh",
        meaning="Have / Possess (Haitian Creole: 'Nou gen' = 'We have')"
    ),
    "ai": PronunciationOverride(
        token="AI",
        target_ipa=HAITIAN_CREOLE_AI_IPA,
        ssml_override='<phoneme alphabet="ipa" ph="eɪ.aɪ">AI</phoneme>',
        phonetic_respelling="A-I",
        meaning="Artificial Intelligence"
    ),
}


def apply_ssml_pronunciation(text: str) -> str:
    """Wrap 'Nou Gen AI' with strict SSML phoneme tags preserving Haitian Creole pronunciation."""
    pattern = re.compile(r'\bNou\s+Gen\s+AI\b', re.IGNORECASE)
    return pattern.sub(CANONICAL_SSML, text)


def apply_phonetic_respelling(text: str) -> str:
    """Deterministic adapter fallback for TTS engines without SSML/IPA support."""
    pattern = re.compile(r'\bNou\s+Gen\s+AI\b', re.IGNORECASE)
    # Uses 3-beat phonetic respelling preventing anglicization to 'New Jen Eye'
    return pattern.sub("Noo Gehng A-I", text)


def validate_brand_pronunciation(text: str) -> Dict[str, Any]:
    """Inspect and verify that brand tokens do not fall back to anglicized defaults."""
    lower = text.lower()
    has_brand = "nou gen ai" in lower or "nou. gen. a-i" in lower
    return {
        "has_brand_mention": has_brand,
        "is_creole_preserved": "ɡɛ̃" in text or "noo gehng" in lower or "nou. gen. a-i." in lower or "ph=\"ɡɛ̃\"" in text,
        "anglicized_detected": bool(re.search(r'\b(jen|generation)\b', text, re.IGNORECASE)) and has_brand
    }
