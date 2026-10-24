"""Schemas of configs/demo.yaml and the endpoint presets."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt


class EndpointConfig(BaseModel):
    """Settings every endpoint preset shares."""

    name: str
    rpm: float | None = Field(default=None, gt=0, description="null: unlimited")
    max_concurrency: PositiveInt = 8


class DemoConfig(BaseModel):
    """Entry config of `demo-run`."""

    run_name: str = Field(
        default="${now:%Y%m%d_%H%M%S}", description="directory under runs/"
    )
    results_dir: Path = Path("runs/${run_name}")
    wandb_project: str = Field(default="demo", description="W&B project")
    workers: PositiveInt = Field(default=4, description="number of workers")
    log_level: Literal["debug", "info", "warning"] = "info"
    poll_interval: PositiveFloat = 5.0
    port: int = Field(default=8080, ge=1, le=65535)
    cache_dir: Path | None = Field(default=None, description="null: no cache")
    max_items: PositiveInt | None = Field(default=None, description="null: unlimited")
    upload: bool = Field(
        default=False, description="true: sends the run's files to the team bucket"
    )
    compaction_interval: PositiveInt = 15
    endpoint: EndpointConfig
