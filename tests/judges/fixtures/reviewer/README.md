# demo

demo

How the code is built and how to change it: [CONTRIBUTING.md](CONTRIBUTING.md).

## Setup

```bash
make setup          # uv sync + git hooks
cp .env.example .env
```

## Daily workflow

1. Run: `demo-run`, overriding anything Hydra-style:
   `demo-run seed=1 run_name=baseline`.
2. Results land in `runs/<run_name>/`: the resolved `config.yaml` (secrets masked), `run.json` (git SHA, dirty flag,
   argv, start time) and the run's outputs.
3. Before committing: `make check`.

## Commands

| command | does |
|---|---|
| `demo-run` | validate the config, seed, start a run directory |
| `demo-configs` | regenerate `configs/` from the config schemas (`--check` only reports) |
| `make help` | list every make target |

## Configs

`configs/defaults/run.yaml` lists every setting with its default, commented where the options or meaning are not
obvious. It is generated from the schema in `src/demo/config.py`, so it is never edited. To change a value:

| for | edit |
|---|---|
| one run | `key=value` on the command line; the run directory records it |
| every run of this repo | `configs/run.yaml`, the entry config, below its `defaults:` list |
| the default itself | the schema, then `make configs` |

Secrets go in `.env` and reach configs as `${oc.env:NAME,null}`.
