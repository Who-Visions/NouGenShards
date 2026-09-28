from nougen_voice.pronunciation import (
    apply_ssml_pronunciation,
    apply_phonetic_respelling,
    validate_brand_pronunciation,
    CANONICAL_SSML,
    HAITIAN_CREOLE_GEN_IPA
)

def test_ssml_pronunciation_injection():
    input_text = "Welcome to Nou Gen AI, where memory is law."
    output_text = apply_ssml_pronunciation(input_text)
    assert CANONICAL_SSML in output_text
    assert HAITIAN_CREOLE_GEN_IPA in output_text

def test_phonetic_respelling_fallback():
    input_text = "Experience the power of Nou Gen AI today."
    output_text = apply_phonetic_respelling(input_text)
    assert "Noo Gehng A-I" in output_text

def test_brand_validation_creole_preservation():
    valid_text = "Nou. Gen. A-I. - In a world where memory is law."
    result = validate_brand_pronunciation(valid_text)
    assert result["has_brand_mention"] is True
    assert result["is_creole_preserved"] is True
    assert result["anglicized_detected"] is False

def test_brand_validation_anglicized_detection():
    # If a prompt or engine attempts to anglicize to 'generation' or 'jen'
    invalid_text = "Nou Gen AI generation models"
    result = validate_brand_pronunciation(invalid_text)
    assert result["has_brand_mention"] is True
    assert result["anglicized_detected"] is True
