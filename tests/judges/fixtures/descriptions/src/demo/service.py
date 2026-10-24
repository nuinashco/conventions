"""The demo run: poll the queue, process items, compact the agent's history."""

from __future__ import annotations

import time

from agentlib import CompactionConfig, compact

from demo.config import DemoConfig
from demo.storage import upload_run


def run(cfg: DemoConfig, queue) -> None:
    """Process up to `max_items` items from `queue`, then upload the run if asked."""
    limit = cfg.max_items or 100
    done = 0
    while done < limit:
        item = queue.get()
        if item is None:
            time.sleep(cfg.poll_interval)
            continue
        item.process(workers=cfg.workers)
        done += 1
    compact(CompactionConfig(compaction_interval=cfg.compaction_interval))
    if cfg.upload:
        upload_run(cfg.results_dir, bucket="gs://team-runs")
