"""Metadata container describing the expected schema for dataset rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MetadataRecord:
    image: str
    question: str
    options: List[str]
    answer: str
    category: str
    difficulty: str
    source: str
    seed: int | None = None
    camera_pose: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)
