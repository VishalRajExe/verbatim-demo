"""Comparison package public API."""
from app.services.comparison.clauses import Clause, aggressive_normalize, split_clauses
from app.services.comparison.materiality import floor_significance
from app.services.comparison.pipeline import compare_texts, comparison_result
from app.services.comparison.similarity import dice

__all__ = [
    "Clause",
    "split_clauses",
    "aggressive_normalize",
    "dice",
    "floor_significance",
    "compare_texts",
    "comparison_result",
]
