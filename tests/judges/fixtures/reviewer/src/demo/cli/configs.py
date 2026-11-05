"""`demo-configs`: regenerate the YAML files that mirror config schemas.

Usage:

    demo-configs            # rewrite stale files in configs/

    demo-configs --check    # fail instead, listing the stale files
"""

import click
import rootutils

from nuikit import configgen, registry
from nuikit.errors import ConfigError, cli_boundary

from demo import paths
from demo.config import GENERATED

# Loads .env and sets PROJECT_ROOT, as every entry point does (GUIDE ENV-2).
rootutils.setup_root(__file__, indicator=".project-root")


@click.command(help=__doc__)
@click.option("--check", is_flag=True, help="Fail if any file is stale.")
@cli_boundary
def main(*, check: bool) -> None:
    files = [*GENERATED, *registry.config_files("demo")]
    if check:
        if stale := configgen.stale(files, paths.CONFIGS_DIR):
            names = ", ".join(str(p.relative_to(paths.ROOT)) for p in stale)
            raise ConfigError(f"stale configs: {names}; run `make configs`")
        return
    for path in configgen.write(files, paths.CONFIGS_DIR):
        click.echo(f"wrote {path.relative_to(paths.ROOT)}")
