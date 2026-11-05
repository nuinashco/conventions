"""`demo-run`: validate configs/run.yaml, seed, and start a run directory.

Usage:

    demo-run                            # configs/run.yaml as it is
    demo-run seed=1 run_name=baseline   # Hydra overrides

Writes runs/<run_name>/ with the resolved config and its provenance.
"""

import hydra
import rootutils
import structlog
from omegaconf import DictConfig

from nuikit import runs, seeding
from nuikit.errors import cli_boundary
from nuikit.logging import configure_logging

from demo import paths
from demo.config import MainConfig

# Loads .env and sets PROJECT_ROOT for ${oc.env:...} in configs.
rootutils.setup_root(__file__, indicator=".project-root")

log = structlog.stdlib.get_logger()


@hydra.main(config_path=str(paths.CONFIGS_DIR), config_name="run")
@cli_boundary
def main(dict_cfg: DictConfig) -> None:
    cfg = MainConfig.from_hydra(dict_cfg)
    configure_logging(level=cfg.log_level, fmt=cfg.log_format)
    seeding.seed_everything(cfg.seed, deterministic=cfg.deterministic)
    run_dir = runs.start_run(cfg, name=cfg.run_name, runs_dir=paths.RUNS_DIR)
    log.info("run_started", run_dir=str(run_dir), seed=cfg.seed)
