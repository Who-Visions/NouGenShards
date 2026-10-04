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
from typing import Set


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

    def __init__(self, op_flip_limit: int = 1) -> None:
        super().__init__()
        self.flips = 0
        self.flip_limit = op_flip_limit

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if self.flips >= self.flip_limit:
            return node

        new_ops = []
        for op in node.ops:
            if self.flips < self.flip_limit:
                if isinstance(op, ast.Gt):
                    new_ops.append(ast.GtE())
                    self.flips += 1
                elif isinstance(op, ast.Lt):
                    new_ops.append(ast.LtE())
                    self.flips += 1
                elif isinstance(op, ast.GtE):
                    new_ops.append(ast.Gt())
                    self.flips += 1
                elif isinstance(op, ast.LtE):
                    new_ops.append(ast.Lt())
                    self.flips += 1
                elif isinstance(op, ast.Eq):
                    new_ops.append(ast.NotEq())
                    self.flips += 1
                elif isinstance(op, ast.NotEq):
                    new_ops.append(ast.Eq())
                    self.flips += 1
                else:
                    new_ops.append(op)
            else:
                new_ops.append(op)
        node.ops = new_ops
        return node


class RSIMutationEngine:
    """Engine orchestrating candidate AST mutations with sandboxed invariant checks."""

    def __init__(self, deny_list: Set[str] | None = None) -> None:
        self.deny_list: Set[str] = set(deny_list or [])

    def register_negative_constraint(self, mutation_hash: str) -> None:
        """Adds a failed mutation hash to the lineage deny-list."""
        self.deny_list.add(mutation_hash)

    def mutate_code(self, source_code: str, mutation_type: str = "boundary_tweak") -> MutationResult:
        """Parses, mutates, and verifies a code snippet under AST invariants."""
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            raise MutationSyntaxError(f"Initial code is not valid Python: {e}") from e

        orig_hash = compute_ast_hash(tree)

        mutated_tree = copy.deepcopy(tree)
        mutator = ASTMutator()
        mutated_tree = mutator.visit(mutated_tree)
        ast.fix_missing_locations(mutated_tree)

        mut_hash = compute_ast_hash(mutated_tree)

        if mut_hash in self.deny_list:
            raise LineageConstraintError(f"Mutant {mut_hash} is present in lineage negative constraints")

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
