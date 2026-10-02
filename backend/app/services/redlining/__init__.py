"""Tracked-changes redlining package public API."""
from app.services.redlining.service import Edit, RedlineResult, apply_redlines
from app.services.redlining.tracked_changes import (
    AppliedEdit,
    apply_tracked_edit,
    count_occurrences,
    count_tracked_changes,
)

__all__ = [
    "Edit",
    "RedlineResult",
    "apply_redlines",
    "AppliedEdit",
    "apply_tracked_edit",
    "count_occurrences",
    "count_tracked_changes",
]
