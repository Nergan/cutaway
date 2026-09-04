"""Boot the Age world headless and report loop health.

A scratch harness rather than a test: it drives a real event loop at the real tick
rate so the numbers mean something. Tests use ManualClock and assert on state.

    python scripts/probe_age.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from age.config import load_settings  # noqa: E402
from age.presentation.container import Container  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")


async def main() -> None:
    settings = dataclasses.replace(
        load_settings(),
        use_mongo=False,
        tier_cooldown_seconds=5.0,
        allow_dev_controls=True,
    )
    container = Container(settings)

    started = time.perf_counter()
    await container.startup()
    await container.ready()
    print(f"boot                {(time.perf_counter() - started) * 1000:7.0f} ms")

    room = container.room
    manager = room.simulation.manager

    await asyncio.sleep(2.0)
    print(f"warmup after 2 s    {manager.warmup_pending():7d} chunks pending")
    _report(room)

    print("forcing tier 1")
    manager.force_tier(1, container.world.now)
    await asyncio.sleep(4.0)

    print(f"warmup after expand {manager.warmup_pending():7d} chunks pending")
    print(f"tier                {container.world.topology.current_tier:7d}")
    print(f"loaded chunks       {len(container.world.loaded_chunks()):7d}")
    states: dict[str, int] = {}
    for record in container.world.topology.chunks.values():
        states[record.state.name] = states.get(record.state.name, 0) + 1
    print(f"chunk states        {states}")
    _report(room)

    await container.shutdown()


def _report(room) -> None:  # noqa: ANN001 - scratch harness
    stats = room.stats
    window = sorted(stats.tick_ms_window)
    p95 = window[int(len(window) * 0.95)] if window else 0.0
    print(
        f"ticks {stats.ticks:5d}  slow {stats.slow_ticks:4d}  "
        f"avg {stats.average_tick_ms:6.2f} ms  p95 {p95:6.2f} ms  "
        f"peak {stats.peak_tick_ms:6.2f} ms"
    )
    print(
        f"warmed {stats.chunks_warmed:4d}  skipped {stats.warmups_skipped:4d}  "
        f"cost estimate {room.simulation.manager.chunk_cost_seconds * 1000:6.2f} ms"
    )


if __name__ == "__main__":
    asyncio.run(main())
