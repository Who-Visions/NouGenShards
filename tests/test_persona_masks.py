"""Unit tests for the 20-pack composable behavioral masks in nougen_shards.persona."""
import pytest
from nougen_shards.persona import (
    BEHAVIORAL_MASKS,
    PERSONAS,
    MaskBlend,
    list_masks,
    get_mask,
    blend,
)

EXPECTED_20_PACK = [
    "charming", "sneaky", "witty", "nerdy", "ditzy",
    "dumb", "sarcastic", "flirty", "stoic", "chaotic",
    "genius", "streetwise", "paranoid", "optimist", "pessimist",
    "dramatic", "professor", "detective", "gremlin", "villain"
]


def test_20_pack_masks_exist():
    """Verify all 20 primitive masks exist in BEHAVIORAL_MASKS and PERSONAS alias."""
    assert len(BEHAVIORAL_MASKS) == 20
    assert BEHAVIORAL_MASKS is PERSONAS
    for name in EXPECTED_20_PACK:
        assert name in BEHAVIORAL_MASKS
        m = BEHAVIORAL_MASKS[name]
        assert "traits" in m and len(m["traits"]) >= 3
        assert "style" in m and len(m["style"]) > 5


def test_list_and_get_mask():
    """Verify mask listing and retrieval helpers."""
    masks = list_masks()
    assert len(masks) == 20
    assert masks == sorted(EXPECTED_20_PACK)

    ditzy = get_mask("ditzy")
    assert ditzy is not None
    assert "scatterbrained" in ditzy["traits"]

    nonexistent = get_mask("nonexistent_mask_xyz")
    assert nonexistent is None


def test_blend_single():
    """Verify blending a single mask."""
    b = blend("stoic")
    assert b.mask_names == ("stoic",)
    assert "disciplined" in b.traits
    assert len(b.styles) == 1
    prompt = b.system_prompt()
    assert "Active Behavioral Mask: Stoic." in prompt
    assert "Dominant Personality Traits:" in prompt
    assert "* [Stoic]:" in prompt


def test_blend_multiple_args():
    """Verify blending multiple discrete masks (e.g. ditzy + genius)."""
    b = blend("ditzy", "genius")
    assert b.mask_names == ("ditzy", "genius")
    assert "scatterbrained" in b.traits
    assert "analytical" in b.traits
    assert len(b.styles) == 2
    prompt = b.system_prompt(base_identity="Kaedra")
    assert "Base Identity: Kaedra." in prompt
    assert "Active Behavioral Mask: Ditzy + Genius." in prompt
    assert "* [Ditzy]:" in prompt
    assert "* [Genius]:" in prompt


def test_blend_delimited_strings():
    """Verify plus-separated and comma-separated string inputs to blend()."""
    b1 = blend("charming+sneaky+witty")
    assert b1.mask_names == ("charming", "sneaky", "witty")
    assert "magnetic" in b1.traits
    assert "cunning" in b1.traits
    assert "playful" in b1.traits

    b2 = blend("witty, sarcastic")
    assert b2.mask_names == ("witty", "sarcastic")
    assert "verbally sharp" in b2.traits
    assert "deadpan" in b2.traits


def test_blend_trait_deduplication():
    """Verify traits are deduplicated in first-seen order across blended masks."""
    b = blend("witty", "flirty")  # Both share playful
    assert b.traits.count("playful") == 1
    # Check that first occurrence order is maintained
    witty_traits = BEHAVIORAL_MASKS["witty"]["traits"]
    for t in witty_traits:
        assert t in b.traits


def test_mask_blend_apply_to():
    """Verify stacking a mask blend on an existing agent system prompt."""
    base_prompt = "You are Dav1d, the infrastructure and operations lead."
    b = blend("streetwise", "paranoid")
    stacked = b.apply_to(base_prompt, base_identity="Dav1d")

    assert stacked.startswith("You are Dav1d, the infrastructure and operations lead.")
    assert "=== BEHAVIORAL MASK ===" in stacked
    assert "Base Identity: Dav1d." in stacked
    assert "Active Behavioral Mask: Streetwise + Paranoid." in stacked
    assert "* [Streetwise]:" in stacked
    assert "* [Paranoid]:" in stacked


def test_blend_custom_unknown_mask():
    """Verify custom mask tokens not in 20-pack resolve gracefully."""
    b = blend("cyberpunk", "stoic")
    assert b.mask_names == ("cyberpunk", "stoic")
    assert "cyberpunk" in b.traits
    assert "calm" in b.traits


def test_20_pack_emotions_exist():
    """Verify all 20 spectrum emotions exist with full metadata."""
    from nougen_shards.persona import EMOTIONS, list_emotions, get_emotion, resolve_emotion

    emotions = list_emotions()
    assert len(emotions) == 20
    assert emotions[0] == "ecstatic"
    assert emotions[-1] == "enraged"

    for name in emotions:
        e = get_emotion(name)
        assert e is not None
        assert "intensity" in e
        assert "valence" in e
        assert "speech_style" in e
        assert "body_language" in e
        assert "decision_bias" in e
        assert "opposite" in e
        assert e["opposite"] in EMOTIONS

    # Verify opposites are symmetrical polar counterparts
    assert get_emotion("ecstatic")["opposite"] == "enraged"
    assert get_emotion("enraged")["opposite"] == "ecstatic"
    assert get_emotion("calm")["opposite"] == "anxious"
    assert get_emotion("anxious")["opposite"] == "calm"


def test_resolve_emotion():
    """Verify resolve_emotion produces valid EmotionState dataclasses."""
    from nougen_shards.persona import resolve_emotion

    es = resolve_emotion("ecstatic")
    assert es.name == "ecstatic"
    assert es.intensity == 1.0
    assert es.valence == "positive"
    prompt = es.system_prompt()
    assert "Active Emotional State: Ecstatic" in prompt
    assert "Speech Style:" in prompt
    assert "Somatic / Body Language:" in prompt
    assert "Polarity Counterpart: Enraged" in prompt

