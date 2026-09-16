"""Unit tests for nougen_shards.emoji_math vector algebra and interaction calculus."""
import pytest
from nougen_shards.emoji_math import (
    SCALE,
    EmojiVector,
    apply_task_modulation,
)


def test_emoji_vector_arithmetic():
    """Verify addition, subtraction, scaling, and blending of emoji vectors."""
    v1 = EmojiVector(warmth=6000, cognition=8000, humor=7000)
    v2 = EmojiVector(warmth=2000, cognition=1000, anger=5000)

    # Addition
    v_add = v1 + v2
    assert v_add.warmth == 8000
    assert v_add.cognition == 9000
    assert v_add.anger == 5000

    # Subtraction
    v_sub = v1 - v2
    assert v_sub.warmth == 4000
    assert v_sub.cognition == 7000
    assert v_sub.anger == 0

    # Scaling
    v_mul = v1 * 0.5
    assert v_mul.warmth == 3000
    assert v_mul.cognition == 4000

    # Blending
    v_blend = v1.blend(v2, alpha_bp=5000)  # 50/50
    assert v_blend.warmth == 4000
    assert v_blend.cognition == 4500
    assert v_blend.anger == 2500


def test_interaction_algebra_constructs():
    """Verify emergent interaction constructs (relational anger, biting sarcasm, analytical investigation)."""
    # 1. 😡 + ❤️ = Relational anger (angry because they care)
    v_rel_anger = EmojiVector(anger=7500, warmth=6500)
    constructs = v_rel_anger.describe_algebra()
    assert any("relational anger" in c for c in constructs)

    # 2. 😂 - ❤️ = Biting sarcasm (high humor, low warmth)
    v_sarcasm = EmojiVector(humor=8500, warmth=1000, cognition=7000)
    constructs_sarcasm = v_sarcasm.describe_algebra()
    assert any("biting/dry sarcasm" in c for c in constructs_sarcasm)

    # 3. 🧠 + 🔍 + 🧪 = Analytical investigation
    v_investigate = EmojiVector(cognition=8500, investigation=8800, verification=9200)
    constructs_inv = v_investigate.describe_algebra()
    assert any("analytical investigation" in c for c in constructs_inv)

    # 4. 😨 - 🛡️ = Panic (high fear, zero caution/defense)
    v_panic = EmojiVector(fear=8000, caution=1000)
    constructs_panic = v_panic.describe_algebra()
    assert any("acute panic" in c for c in constructs_panic)


def test_task_operators():
    """Verify task triggers modulate emoji vectors predictably."""
    baseline = EmojiVector(
        warmth=5000,
        cognition=5000,
        investigation=5000,
        verification=5000,
        humor=5000,
        energy=5000,
    )

    # Debug: 🐛 → 🧠↑ + 🔍↑ + 🧪↑ + 🎯↑ + 😂↓
    debug_state = apply_task_modulation(baseline, "🐛")
    assert debug_state.cognition > 7500
    assert debug_state.investigation > 7500
    assert debug_state.verification > 8000
    assert debug_state.humor < 2000

    # Celebration: 🎉 → 😊↑ + ❤️↑ + ⚡↑ + 😂↑ + 🧪↓
    celeb_state = apply_task_modulation(baseline, "🎉")
    assert celeb_state.positive > 8000
    assert celeb_state.warmth > 7500
    assert celeb_state.energy > 8000
    assert celeb_state.humor > 7500
    assert celeb_state.verification < 3000

    # Grief: 💔 → ❤️↑ + 😢↑ + ⚡↓ + 😂↓↓ + 🤫↑
    grief_state = apply_task_modulation(baseline, "💔")
    assert grief_state.warmth > 8500
    assert grief_state.sadness > 7500
    assert grief_state.humor < 1000
    assert grief_state.energy < 2500
    assert grief_state.restraint > 8000


def test_receipt_formatting():
    """Verify compact formatting and one-line algebraic receipt output."""
    v = EmojiVector(
        warmth=3100,
        cognition=8800,
        investigation=7400,
        verification=9100,
        humor=2200,
        caution=6700,
    )

    compact = v.to_compact_string(threshold_bp=3000)
    assert "❤️31" in compact
    assert "🧠88" in compact
    assert "🔍74" in compact
    assert "🧪91" in compact

    receipt = v.one_line_receipt()
    assert receipt.startswith("🎭 = ")
    assert "0.91🧪" in receipt
    assert "0.88🧠" in receipt
    assert "0.74🔍" in receipt


def test_smart_emoji_signal_synthesis():
    """Verify smart semantic emoji channel selection, density, and formatting."""
    from nougen_shards.emoji_math import synthesize_smart_emojis

    # 1. Incident / Danger -> 🚨 or 🛡️ in top candidates
    v_incident = EmojiVector(urgency=9500, caution=9500, fear=8000, investigation=9000, verification=9500)
    sig_incident = synthesize_smart_emojis(v_incident, urgency_bp=9500)
    assert sig_incident.density >= 2
    assert "🚨" in sig_incident.semantic_combo or "🛡️" in sig_incident.semantic_combo
    msg_inc = sig_incident.format_message("Potential compromise detected.")
    assert "Potential compromise detected." in msg_inc

    # 2. Celebration -> Postfix with high energy
    v_celebrate = EmojiVector(positive=9500, energy=9500, warmth=8500, success=9500, verification=7000)
    sig_celeb = synthesize_smart_emojis(v_celebrate)
    assert sig_celeb.density >= 2
    assert sig_celeb.position == "postfix"
    msg_celeb = sig_celeb.format_message("We got it working.")
    assert msg_celeb.endswith(sig_celeb.semantic_combo)

    # 3. Grief -> Zero Emojis (Mathematical Restraint)
    v_grief = EmojiVector(sadness=9000, warmth=9500, restraint=9000, energy=1500)
    sig_grief = synthesize_smart_emojis(v_grief)
    assert sig_grief.density == 0
    assert sig_grief.semantic_combo == ""
    msg_grief = sig_grief.format_message("I am here with you.")
    assert msg_grief == "I am here with you."

    # 4. Telemetry Compact
    assert len(sig_incident.telemetry_compact) >= 2


def test_dynamic_glyph_discovery_and_inference():
    """Verify runtime discovery of Unicode glyphs and semantic affinity inference without code changes."""
    from nougen_shards.emoji_math import DynamicGlyphRegistry, EmojiVector, emoji_renderer

    registry = DynamicGlyphRegistry()

    # Discover and infer affinities for a robot glyph
    descriptor_robot = registry.infer_and_register(
        glyph="🤖",
        name="robot",
        description="automated mechanical cognition and verification agent",
        keywords=("think", "robot", "gear"),
    )
    assert descriptor_robot.cognition >= 8000
    assert descriptor_robot.verification >= 7000
    assert descriptor_robot.role == "action" or descriptor_robot.role == "state"

    # Discover and infer affinities for ice (stoic restraint)
    descriptor_ice = registry.infer_and_register(
        glyph="🧊",
        name="ice",
        description="cold stoic restraint and focus",
        keywords=("ice", "restraint"),
    )
    assert descriptor_ice.restraint >= 9000

    # In a cold, robotic verification state, 🤖 or 🧊 emerges from dynamic registry
    v_robot = EmojiVector(cognition=9200, verification=9500, restraint=8500, warmth=1000, humor=0)
    sig = emoji_renderer(v_robot, registry=registry)
    assert sig.density >= 1
    assert "🤖" in sig.semantic_combo or "🧪" in sig.semantic_combo or "🧠" in sig.semantic_combo


def test_contradiction_and_compatibility_filtering():
    """Verify that mutually contradictory glyphs are suppressed in top selections."""
    from nougen_shards.emoji_math import (
        GlyphDescriptor,
        compute_glyph_compatibility,
        EmojiVector,
    )

    g_check = GlyphDescriptor("✅", "success", role="result", positive=9000, success=9000)
    g_cross = GlyphDescriptor("❌", "failure", role="result", sadness=7000, failure=9000)

    # In unambiguous success state, ✅ and ❌ have high contradiction penalty
    v_success = EmojiVector(positive=9000, success=9000, uncertainty=1000)
    compat = compute_glyph_compatibility(g_check, g_cross, v_success)
    assert compat < -5000

    # In high uncertainty/ambiguity state, penalty is softened
    v_ambivalent = EmojiVector(positive=5000, uncertainty=8500)
    compat_amb = compute_glyph_compatibility(g_check, g_cross, v_ambivalent)
    assert compat_amb > -3000


def test_unified_canonical_behavior_state_projection():
    """Verify CanonicalBehaviorState projects identically across NL directives, emoji envelopes, and telemetry."""
    from nougen_shards.behavior import (
        BehavioralState,
        SemanticObservation,
        TaskRequirements,
        IntentDescriptor,
        RelationshipContext,
        EpistemicState,
        compile_behavior,
    )

    obs = SemanticObservation(
        raw_input="Verify all systems before deployment.",
        intent=IntentDescriptor(primary="verify_systems"),
        task=TaskRequirements(
            task_type="technical_verification",
            precision_requirement_bp=9500,
            verification_pressure_bp=9500,
            complexity_bp=8000,
        ),
        relationship=RelationshipContext(closeness_bp=6000, formality_requirement_bp=2000),
        epistemic=EpistemicState(known_ratio_bp=4000, unknown_ratio_bp=6000),
        emotional_energy_bp=6500,
        positive_affect_bp=4000,
        urgency_bp=7000,
    )

    compiled = compile_behavior(obs, base_identity="Yukiai")

    # 1. State contains canonical basis points
    state = compiled.state
    assert state.verification_pressure >= 9000
    assert state.technical_depth >= 8000

    # 2. NL Directives match verification and depth
    nl_directives = compiled.natural_language_directives()
    assert "verification" in nl_directives.lower() or "rigor" in nl_directives.lower()

    # 3. Emoji envelope reflects verification actions
    envelope = compiled.emoji_envelope()
    assert envelope.density >= 1
    assert "🧪" in envelope.semantic_combo or "🔍" in envelope.semantic_combo or "🧠" in envelope.semantic_combo

    # 4. Telemetry receipt reflects exact basis points
    telemetry = compiled.telemetry_receipt()
    assert "🧪" in telemetry
    assert "🧠" in telemetry

    # 5. System prompt integrates telemetry receipt
    sys_prompt = compiled.system_prompt()
    assert "Telemetry Receipt:" in sys_prompt


