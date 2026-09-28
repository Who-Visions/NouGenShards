from nougen_voice.veo_gem import (
    VeoShotSpecification,
    compile_veo_prompt
)

def test_veo_shot_frame_math():
    spec = VeoShotSpecification(duration_seconds=5.0, fps=24, action_intent="Reika reaches toward tear")
    assert spec.total_frames == 120

def test_veo_background_parity_lock():
    spec = VeoShotSpecification(
        duration_seconds=4.5,
        fps=24,
        action_intent="Severity falls to ground with metallic ring",
        continuity_prior_state="Xoah 2 hand recoils into shadow smoke"
    )
    result = compile_veo_prompt(spec)
    prompt = result["prompt"]
    assert "[CONTINUITY RESTRICTION]" in prompt
    assert "[BACKGROUND PARITY LOCK]" in prompt
    assert "Horizon fixed at 38% frame height" in prompt
    assert "pyramid caldera rim left-to-right" in prompt
    assert result["timing"]["total_frames"] == 108
    assert "zero_horizon_drift" in result["parity_rules_enforced"]
