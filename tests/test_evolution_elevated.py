import math
import pytest
from nougen_shards.evolution_elevated import (
    SkillGene,
    SkillChromosome,
    EvolutionFitnessEngine,
)


def test_fitness_evaluation():
    engine = EvolutionFitnessEngine(lambda_complexity=0.1)
    genes = [
        SkillGene(gene_id="g1", success_rate=1.0, execution_latency_ms=10.0, complexity=1.0),
        SkillGene(gene_id="g2", success_rate=0.9, execution_latency_ms=20.0, complexity=2.0),
    ]
    chrom = SkillChromosome(skill_id="s1", genes=genes)

    fitness = engine.evaluate_fitness(chrom)
    assert fitness > 0.0
    assert chrom.fitness == fitness
    assert chrom.total_complexity == 3.0


def test_selection_probabilities_softmax():
    engine = EvolutionFitnessEngine(temperature=1.0, seed=42)
    c1 = SkillChromosome(skill_id="c1", genes=[SkillGene(gene_id="g1", success_rate=1.0, complexity=1.0)])
    c2 = SkillChromosome(skill_id="c2", genes=[SkillGene(gene_id="g2", success_rate=0.5, complexity=5.0)])

    probs = engine.selection_probabilities([c1, c2])
    assert len(probs) == 2
    assert sum(probs) == pytest.approx(1.0, 1e-5)
    assert probs[0] > probs[1]  # higher fitness has higher selection probability


def test_crossover_recombination():
    engine = EvolutionFitnessEngine(seed=1337)
    p1 = SkillChromosome(skill_id="p1", genes=[SkillGene(gene_id="g1", weight=1.0)], generation=1)
    p2 = SkillChromosome(skill_id="p2", genes=[SkillGene(gene_id="g1", weight=2.0)], generation=1)

    child = engine.crossover(p1, p2, "child_1")
    assert child.generation == 2
    assert len(child.genes) == 1
    assert child.genes[0].weight == 1.5


def test_diversity_entropy():
    engine = EvolutionFitnessEngine()
    # Uniform population of 2 unique genes equally split -> H = 1.0 bit
    pop = [
        SkillChromosome(skill_id="c1", genes=[SkillGene(gene_id="A")]),
        SkillChromosome(skill_id="c2", genes=[SkillGene(gene_id="B")]),
    ]
    entropy = engine.calculate_diversity_entropy(pop)
    assert pytest.approx(entropy, 1e-5) == 1.0


def test_parent_selection_reproducible():
    engine1 = EvolutionFitnessEngine(seed=999)
    engine2 = EvolutionFitnessEngine(seed=999)

    pop = [
        SkillChromosome(skill_id="c1", genes=[SkillGene(gene_id="A", success_rate=0.9)]),
        SkillChromosome(skill_id="c2", genes=[SkillGene(gene_id="B", success_rate=0.8)]),
    ]
    sel1 = engine1.select_parent(pop)
    sel2 = engine2.select_parent(pop)
    assert sel1.skill_id == sel2.skill_id
