"""
Unit tests for reasoning_governor_elevated module.
"""
from nougen_shards.reasoning_governor import TrajectoryCheckpoint, ConsequenceClass, TaskClass, ReasoningValueBucket
from nougen_shards.reasoning_governor_elevated import (
    compute_epistemic_confidence_interval,
    evaluate_tensorized_marginal_value,
    CognitiveUtilityTensor
)

def test_epistemic_confidence_interval():
    center, lower, upper = compute_epistemic_confidence_interval(8, 10)
    assert 0.0 <= lower <= center <= upper <= 1.0
    assert lower > 0.45

def test_tensorized_marginal_value():
    cp = TrajectoryCheckpoint(
        trajectory_id="traj_001",
        step_index=1,
        task_class=TaskClass.SYSTEM_ARCHITECTURE,
        consequence_class=ConsequenceClass.C3_STATEFUL_MUTATION,
        contradictions_count=1,
        subgoals_total=2,
        subgoals_completed=0,
        unresolved_constraints=2
    )
    tensor, bucket, reason = evaluate_tensorized_marginal_value(cp)
    assert isinstance(tensor, CognitiveUtilityTensor)
    assert tensor.quality_gain > 0
    assert bucket in (ReasoningValueBucket.HIGH_POSITIVE, ReasoningValueBucket.LOW_POSITIVE)
    assert reason == "high_utility_cognition_licensed"
