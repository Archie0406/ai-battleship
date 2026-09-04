"""
ai/genetic.py
=============
Optional advanced feature: a genetic algorithm that evolves targeting
strategies (or fleet placements) across simulated games, as a
population-based alternative to the analytical approaches elsewhere
in this package.

Planned pieces: Individual (a targeting policy encoded as a gene
sequence), fitness = average shots-to-win over simulated games,
selection, crossover, and mutation operators.
"""


class Individual:
    def __init__(self, genes):
        self.genes = genes
        self.fitness = None


class GeneticAlgorithm:
    def __init__(self, population_size=50, mutation_rate=0.05):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.population = []

    def initialize_population(self):
        """TODO: seed a random initial population of Individuals."""
        raise NotImplementedError

    def evaluate_fitness(self, individual):
        """TODO: simulate games and score the individual."""
        raise NotImplementedError

    def select_parents(self):
        """TODO: e.g. tournament or roulette-wheel selection."""
        raise NotImplementedError

    def crossover(self, parent_a, parent_b):
        """TODO: combine two gene sequences into a child."""
        raise NotImplementedError

    def mutate(self, individual):
        """TODO: randomly perturb genes at self.mutation_rate."""
        raise NotImplementedError

    def evolve(self, generations=100):
        """TODO: run the full generational loop."""
        raise NotImplementedError
