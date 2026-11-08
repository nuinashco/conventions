---
paths:
  - "src/**/*.py"
  - "scripts/**"
  - "notebooks/**"
  - "configs/**/*.yaml"
  - ".gitignore"
---

# Reproducibility, notebooks and data

Rules of [nuinashco/rnd-template](https://github.com/nuinashco/rnd-template). What every run writes and how it is
seeded (RUN-1, RUN-2) are nuikit's rules, carried by the `nuikit` plugin.

### RUN-3 MUST

Pin what can't be seeded:

- Hugging Face model revisions (commit SHA);
- dataset revisions;
- Docker image digests;
- `uv.lock`.

*Check:* review; a test that rejects unpinned model configs where models are configured.

### RUN-4 MAY [rnd]

Setting `tracker: wandb` mirrors a run to Weights & Biases. The run directory stays the source of truth. This project
was made without it: `copier update --trust --data use_wandb=true` adds the setting and the `nuikit[wandb]` extra.

*Check:* review.

### RUN-5 MUST

Notebooks are for exploration: `notebooks/NN-topic.ipynb`, outputs stripped, never imported. Logic worth reusing moves
into `src/` with a test. Third-party notebooks go in `notebooks/reference/`.

*Why:* "notebooks are for exploration and communication, source files are for repetition"
([Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/opinions/)).

*Check:* nbstripout pre-commit hook.

### RUN-6 MUST

Raw data is immutable and gitignored. Downloads are idempotent (write a `.part` file, then rename) and verified by size
or SHA.

*Check:* review.

### RUN-7 SHOULD

The storage format follows the data's role:

- CSV for raw data as received;
- parquet for derived tables;
- JSON for metrics (`ensure_ascii=False, indent=2`);
- NPZ for arrays.

*Check:* review.
