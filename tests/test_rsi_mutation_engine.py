from __future__ import annotations

import pytest
from nougen_shards.rsi_mutation_engine import (
    RSIMutationEngine,
    MutationSyntaxError,
    LineageConstraintError,
    compute_ast_hash,
    compute_ast_jaccard_distance,
)
import ast


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
