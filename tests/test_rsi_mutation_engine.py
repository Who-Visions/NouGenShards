from __future__ import annotations

import pytest
from nougen_shards.rsi_mutation_engine import (
    RSIMutationEngine,
    MutationSyntaxError,
    LineageConstraintError,
)


def test_mutation_engine_boundary_flip():
    code = "def check_score(x):\n    if x > 10:\n        return True\n    return False\n"
    engine = RSIMutationEngine()
    result = engine.mutate_code(code)

    assert result.original_hash != result.mutated_hash
    assert ">=" in result.mutated_code
    assert result.ast_distance >= 0.0


def test_mutation_engine_rejects_negative_constraint():
    code = "def check_score(x):\n    if x > 10:\n        return True\n    return False\n"
    engine = RSIMutationEngine()
    res1 = engine.mutate_code(code)

    # Blacklist the resulting mutation
    engine.register_negative_constraint(res1.mutated_hash)

    with pytest.raises(LineageConstraintError):
        engine.mutate_code(code)


def test_mutation_engine_rejects_invalid_syntax():
    engine = RSIMutationEngine()
    with pytest.raises(MutationSyntaxError):
        engine.mutate_code("def broken_code(:")


TWO_CMP = "def f(x, y):\n    if x > 10:\n        return 1\n    if y < 3:\n        return 2\n    return 0\n"


def test_denied_first_candidate_falls_through_to_next():
    engine = RSIMutationEngine()
    first = engine.mutate_code(TWO_CMP)
    assert "x >= 10" in first.mutated_code and "y < 3" in first.mutated_code
    engine.register_negative_constraint(first.mutated_hash)
    second = engine.mutate_code(TWO_CMP)
    assert "x > 10" in second.mutated_code and "y <= 3" in second.mutated_code
    engine.register_negative_constraint(second.mutated_hash)
    with pytest.raises(LineageConstraintError):
        engine.mutate_code(TWO_CMP)


def test_context_scoped_constraint_does_not_leak():
    engine = RSIMutationEngine()
    first = engine.mutate_code(TWO_CMP)
    engine.register_negative_constraint(first.mutated_hash, context="task-A")
    assert engine.mutate_code(TWO_CMP, context="task-B").mutated_hash == first.mutated_hash
    assert engine.mutate_code(TWO_CMP).mutated_hash == first.mutated_hash
    assert engine.mutate_code(TWO_CMP, context="task-A").mutated_hash != first.mutated_hash


def test_unsupported_mutation_type_is_rejected():
    with pytest.raises(ValueError):
        RSIMutationEngine().mutate_code(TWO_CMP, mutation_type="rewrite_everything")
