"""Schemas of the entry configs; `make configs` mirrors them to configs/defaults/."""

from pydantic import Field

from nuikit.config import Schema
from nuikit.configgen import ConfigFile
from nuikit.logging import LogFormat, LogLevel


class MainConfig(Schema):
    """Entry config of `demo-run` (configs/run.yaml)."""

    run_name: str = Field(
        default="${now:%Y-%m-%d_%H-%M-%S}", description="directory under runs/"
    )
    seed: int = 42
    deterministic: bool = Field(
        default=False, description="true: deterministic torch kernels, slower"
    )
    log_level: LogLevel = Field(default="info", description="debug|info|warning|error")
    log_format: LogFormat = Field(
        default="auto",
        description="auto|console|json; auto: console in a terminal, JSON otherwise",
    )


GENERATED = (ConfigFile("defaults/run.yaml", MainConfig),)
