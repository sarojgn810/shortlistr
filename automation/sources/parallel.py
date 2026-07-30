"""Thread-pool parallel helpers for watchlist ATS fetch."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def parallel_flat_map(
    items: list[T],
    fn: Callable[[T], list[R]],
    *,
    max_workers: int = 10,
) -> list[R]:
    if not items:
        return []
    out: list[R] = []
    workers = min(max_workers, max(1, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(fn, item) for item in items]
        for fut in as_completed(futures):
            try:
                chunk = fut.result()
                if chunk:
                    out.extend(chunk)
            except Exception:
                pass
    return out


def parallel_call(
    fns: list[Callable[[], R]],
    *,
    max_workers: int | None = None,
) -> list[R]:
    if not fns:
        return []
    workers = max_workers or min(10, len(fns))
    out: list[R] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(fn) for fn in fns]
        for fut in as_completed(futures):
            try:
                out.append(fut.result())
            except Exception:
                pass
    return out
