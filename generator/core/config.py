"""Configuration container for generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass
class GenerationConfig:
    num_questions: int = 10
    image_resolution: Tuple[int, int] = (640, 480)
    num_distractors: int = 3
    distractor_difficulty: float = 0.7
    num_cells_min: int = 5
    num_cells_max: int = 15
    rectangular_prism_prob: float = 0.3
    use_rectangular_prisms: bool = True
    camera_distance_factor: float = 1.0
    render_engine: str = "CYCLES"
    ortho_scale: float = 15.0
    use_gpu: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationConfig":
        base = dict(data)
        extra = {k: base.pop(k) for k in list(base.keys()) if not hasattr(cls, k)}
        cfg = cls(**{k: base[k] for k in base})
        cfg.extra = extra
        return cfg
