"""Multi-objective site & massing optimization package.

Wraps and EXTENDS the existing view optimization (view_optimizer wraps
view_optimization_runtime). Each module is a scoring function
score(candidate, ctx) -> {score, metrics, reason}; multi_objective_optimizer
blends them with optimization_weights and produces diverse, named strategy
options. The existing view-only pipeline is untouched and reused.
"""
from . import multi_objective_optimizer, optimization_weights  # noqa: F401

__all__ = ["multi_objective_optimizer", "optimization_weights"]
