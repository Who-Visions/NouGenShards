"""
Evolution Elevated Module: Autonomous Skill Synthesis & Fitness Landscape Dynamics

Implements mathematical formulations for evolutionary skill optimization,
fitness landscape modeling, tournament mutation selection, and genetic diversity entropy.

Mathematical Formulations:
1. Multi-Objective Fitness Evaluation:
   F(s) = sum_k(w_k * f_k(s)) - lambda_penalty * Complexity(s)

2. Softmax Mutation Selection Probability:
   P(select_i) = exp(F(s_i) / tau) / sum_j(exp(F(s_j) / tau))

3. Vector Recombination & Mutation:
   v_child = alpha * v_p1 + (1 - alpha) * v_p2 + N(0, sigma^2)

4. Population Diversity Shannon Entropy:
   H(Pop) = - sum_c(p_c * log2(p_c))
"""

from dataclasses import dataclass, field
import math
import random
from typing import Dict, List, Optional, Tuple


@dataclass
class SkillGene:
    gene_id: str
    weight: float = 1.0
    complexity: float = 1.0
    execution_latency_ms: float = 10.0
    success_rate: float = 0.95


@dataclass
class SkillChromosome:
    skill_id: str
    genes: List[SkillGene] = field(default_factory=list)
    generation: int = 0
    fitness: float = 0.0

    @property
    def total_complexity(self) -> float:
        return sum(g.complexity for g in self.genes)

    @property
    def mean_latency(self) -> float:
        if not self.genes:
            return 0.0
        return sum(g.execution_latency_ms for g in self.genes) / len(self.genes)

    @property
    def average_success_rate(self) -> float:
        if not self.genes:
            return 1.0
        return sum(g.success_rate for g in self.genes) / len(self.genes)


class EvolutionFitnessEngine:
    """
    Evaluates multi-objective fitness landscapes and drives genetic recombination.
    """

    def __init__(self, lambda_complexity: float = 0.05, temperature: float = 1.0, seed: Optional[int] = None):
        self.lambda_complexity = lambda_complexity
        self.temperature = max(1e-5, temperature)
        self.rng = random.Random(seed) if seed is not None else random.Random()

    def evaluate_fitness(self, chrom: SkillChromosome) -> float:
        """
        Computes F(s) = (w1 * success_rate + w2 * latency_score) - lambda * Complexity(s)
        """
        w_success = 0.7
        w_latency = 0.3

        # Latency penalty: 1 / (1 + latency/100)
        latency_score = 1.0 / (1.0 + (chrom.mean_latency / 100.0))
        raw_fitness = (w_success * chrom.average_success_rate) + (w_latency * latency_score)
        penalized_fitness = raw_fitness - (self.lambda_complexity * (chrom.total_complexity / 10.0))

        chrom.fitness = max(0.0, penalized_fitness)
        return chrom.fitness

    def selection_probabilities(self, population: List[SkillChromosome]) -> List[float]:
        """
        Computes Boltzmann softmax selection probabilities.
        """
        if not population:
            return []

        fitnesses = [self.evaluate_fitness(c) for c in population]
        exp_fits = [math.exp(f / self.temperature) for f in fitnesses]
        total_exp = sum(exp_fits)

        if total_exp == 0.0:
            return [1.0 / len(population)] * len(population)
        return [ef / total_exp for ef in exp_fits]

    def select_parent(self, population: List[SkillChromosome]) -> SkillChromosome:
        """
        Samples a parent using computed selection probabilities.
        """
        probs = self.selection_probabilities(population)
        r = self.rng.random()
        cumulative = 0.0
        for ind, p in zip(population, probs):
            cumulative += p
            if r <= cumulative:
                return ind
        return population[-1]

    def crossover(self, p1: SkillChromosome, p2: SkillChromosome, child_id: str) -> SkillChromosome:
        """
        Recombines genes from two parents using uniform crossover.
        """
        child_genes = []
        max_len = max(len(p1.genes), len(p2.genes))

        for i in range(max_len):
            gene1 = p1.genes[i] if i < len(p1.genes) else None
            gene2 = p2.genes[i] if i < len(p2.genes) else None

            if gene1 and gene2:
                # Blend weights and inherit
                chosen = gene1 if self.rng.random() < 0.5 else gene2
                blended_weight = 0.5 * (gene1.weight + gene2.weight)
                child_genes.append(SkillGene(
                    gene_id=chosen.gene_id,
                    weight=blended_weight,
                    complexity=chosen.complexity,
                    execution_latency_ms=0.5 * (gene1.execution_latency_ms + gene2.execution_latency_ms),
                    success_rate=0.5 * (gene1.success_rate + gene2.success_rate),
                ))
            elif gene1:
                child_genes.append(gene1)
            elif gene2:
                child_genes.append(gene2)

        return SkillChromosome(
            skill_id=child_id,
            genes=child_genes,
            generation=max(p1.generation, p2.generation) + 1,
        )

    def calculate_diversity_entropy(self, population: List[SkillChromosome]) -> float:
        """
        Computes Shannon entropy H(Pop) of gene presence distribution across the population.
        """
        if not population:
            return 0.0

        gene_counts: Dict[str, int] = {}
        total_genes = 0

        for chrom in population:
            for g in chrom.genes:
                gene_counts[g.gene_id] = gene_counts.get(g.gene_id, 0) + 1
                total_genes += 1

        if total_genes == 0:
            return 0.0

        entropy = 0.0
        for count in gene_counts.values():
            p = count / total_genes
            if p > 0.0:
                entropy -= p * math.log2(p)

        return max(0.0, entropy)
