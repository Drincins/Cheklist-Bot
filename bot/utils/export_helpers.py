from __future__ import annotations

from dataclasses import replace
from typing import Optional

from ..report_data import AttemptData
from .timezone import to_moscow


def prepare_attempt_for_export(data: AttemptData, department_override: Optional[str] = None) -> AttemptData:
    """Return a copy of AttemptData adjusted for export use (timezone, overrides)."""
    local_dt = to_moscow(data.submitted_at) or data.submitted_at
    updated = replace(data, submitted_at=local_dt)
    if department_override:
        updated = replace(updated, department=department_override)
    return updated
