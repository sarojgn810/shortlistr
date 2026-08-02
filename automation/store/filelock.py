"""Advisory file locking that works on Windows as well as POSIX.

`fcntl` is Unix-only. It was imported unconditionally in two places — the
migration guard in `store/db.py` and the ingest tick lock — so on Windows every
single database call raised ModuleNotFoundError. A clone booted, served /health,
and then 500'd on /setup/status, /pipeline/stats, /cv/status and /cv/upload:
onboarding could not get past the résumé step.

The lock exists to stop two processes running migrations at the same moment. It
is a nicety, not a correctness requirement — SQLite serialises writers itself.
So when the platform offers no locking primitive, callers are told they hold the
lock and carry on, because refusing to work is far worse than a rare retry.
"""

from __future__ import annotations

import errno
from typing import IO

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    msvcrt = None  # type: ignore[assignment]


def acquire(fh: IO, *, blocking: bool = True) -> bool:
    """Take an exclusive lock on ``fh``.

    Returns False only when ``blocking`` is False and somebody else holds it.
    Returns True when the lock was taken *or* when this platform has no locking
    to offer — see the module docstring for why that is deliberate.
    """
    if fcntl is not None:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fh, flags)
            return True
        except OSError as exc:
            if not blocking and exc.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise

    if msvcrt is not None:
        # Windows locks a byte range from the current position, so rewind first.
        # LK_LOCK retries for about ten seconds before giving up.
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), mode, 1)
            return True
        except OSError:
            # Held by someone else. A non-blocking caller wants to know; a
            # blocking one has already waited out the retries, and waiting
            # forever would hang boot.
            return bool(blocking)

    return True


def release(fh: IO) -> None:
    """Drop the lock. Never raises — the caller is already on its way out."""
    if fcntl is not None:
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        except OSError:
            pass
        return

    if msvcrt is not None:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


def available() -> bool:
    """Whether real locking is in force. For diagnostics, not control flow."""
    return fcntl is not None or msvcrt is not None
