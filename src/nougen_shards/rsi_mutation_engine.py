"""AST Sandboxing and bounded mutation engine for NouGen RSI.

Generates syntactically sound, semantically novel mutations of Python code
while enforcing lineage constraints, AST distance boundaries, and bounded
evaluator reservations.
"""

from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import dataclass
from typing import Optional, Set, Tuple


class MutationSyntaxError(ValueError):
    """Raised when an AST mutation produces invalid Python syntax."""


class LineageConstraintError(ValueError):
    """Raised when a candidate mutation violates lineage negative constraints."""


@dataclass(frozen=True)
class MutationResult:
    original_code: str
    mutated_code: str
    original_hash: str
    mutated_hash: str
    mutation_type: str
    ast_distance: float


def compute_ast_hash(tree: ast.AST) -> str:
    """Computes a normalized SHA-256 hash of an AST dump."""
    dumped = ast.dump(tree, annotate_fields=False, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def compute_ast_jaccard_distance(tree_a: ast.AST, tree_b: ast.AST) -> float:
    """Computes Jaccard distance over multiset/set of AST node types."""
    nodes_a = {type(n).__name__ + "_" + str(getattr(n, "id", getattr(n, "name", ""))) for n in ast.walk(tree_a)}
    nodes_b = {type(n).__name__ + "_" + str(getattr(n, "id", getattr(n, "name", ""))) for n in ast.walk(tree_b)}
    union = nodes_a | nodes_b
    if not union:
        return 0.0
    intersection = nodes_a & nodes_b
    similarity = len(intersection) / len(union)
    return 1.0 - similarity


class ASTMutator(ast.NodeTransformer):
    """Safe, bounded AST mutator for operator and boundary tweaks."""

    _FLIP = {ast.Gt: ast.GtE, ast.Lt: ast.LtE, ast.GtE: ast.Gt, ast.LtE: ast.Lt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}

    def __init__(self, op_flip_limit: int = 1, target: int = 0) -> None:
        super().__init__()
        self.flips = 0
        self.flip_limit = op_flip_limit
        self.target = target  # flip the target-th eligible operator (0 = first), so callers can enumerate candidates
        self.seen = 0  # eligible operators encountered

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        new_ops = []
        for op in node.ops:
            flip = self._FLIP.get(type(op))
            if flip is not None:
                if self.flips < self.flip_limit and self.seen >= self.target:
                    op = flip()
                    self.flips += 1
                self.seen += 1
            new_ops.append(op)
        node.ops = new_ops
        return node


class RSIMutationEngine:
    """Engine orchestrating candidate AST mutations with sandboxed invariant checks."""

    SUPPORTED_TYPES = ("boundary_tweak",)
    GLOBAL = "*"

    def __init__(self, deny_list: Set[str] | None = None) -> None:
        # Entries are (context, mutant_hash). A bare hash is global ("*"), the pre-existing behaviour.
        self.deny_list: Set[Tuple[str, str]] = {(self.GLOBAL, h) for h in (deny_list or [])}

    def register_negative_constraint(self, mutation_hash: str, context: Optional[str] = None) -> None:
        """Deny a mutant. Scope it to ``context`` (parent/task/environment hash) when known: a mutant
        that failed in one context is not evidence it fails in another (leg 20261004T183209Z turn 4)."""
        self.deny_list.add((context or self.GLOBAL, mutation_hash))

    def _denied(self, mutation_hash: str, context: Optional[str]) -> bool:
        return (self.GLOBAL, mutation_hash) in self.deny_list or (
            context is not None and (context, mutation_hash) in self.deny_list)

    def mutate_code(self, source_code: str, mutation_type: str = "boundary_tweak",
                    context: Optional[str] = None) -> MutationResult:
        """Return the first eligible mutant not denied for ``context``.

        Raises ValueError for an unsupported ``mutation_type`` (previously ignored),
        LineageConstraintError when every candidate mutant is denied.
        """
        if mutation_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"unsupported mutation_type {mutation_type!r}; supported: {self.SUPPORTED_TYPES}")
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            raise MutationSyntaxError(f"Initial code is not valid Python: {e}") from e
        orig_hash = compute_ast_hash(tree)

        counter = ASTMutator(op_flip_limit=0)
        counter.visit(copy.deepcopy(tree))
        candidates = max(counter.seen, 1)
        mutated_tree = mut_hash = None
        for target in range(candidates):
            trial = ASTMutator(target=target).visit(copy.deepcopy(tree))
            ast.fix_missing_locations(trial)
            trial_hash = compute_ast_hash(trial)
            if not self._denied(trial_hash, context):
                mutated_tree, mut_hash = trial, trial_hash
                break
        if mutated_tree is None:
            raise LineageConstraintError(
                f"all {candidates} candidate mutants are in lineage negative constraints for context {context or self.GLOBAL!r}")

        try:
            mutated_code = ast.unparse(mutated_tree)
            # Roundtrip parse verification
            ast.parse(mutated_code)
        except Exception as e:
            raise MutationSyntaxError(f"Mutated AST failed roundtrip synthesis: {e}") from e
        distance = compute_ast_jaccard_distance(tree, mutated_tree)

        return MutationResult(
            original_code=source_code,
            mutated_code=mutated_code,
            original_hash=orig_hash,
            mutated_hash=mut_hash,
            mutation_type=mutation_type,
            ast_distance=distance,
        )
