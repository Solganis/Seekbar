import queue
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from seekbar.search import MAX_RESULTS, SKIP_DIRS, _matches, _score

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# Seconds between interruption/limit checks while waiting for the backend to emit a line.
_POLL_INTERVAL = 0.1
# Seconds with no output before giving up on a backend that has hung without producing anything.
_IDLE_TIMEOUT = 30.0


def _read_lines(stream: Iterable[str], out_queue: queue.Queue[str | None]) -> None:
    try:
        for line in stream:
            out_queue.put(line)
    finally:
        out_queue.put(None)  # always signal EOF so the consumer never blocks forever


def subprocess_search(
    command: list[str],
    normalized_query: str,
    tokens: list[str],
    on_found: Callable[[str, int, int, bool], object],
    is_interrupted: Callable[[], bool],
) -> int:
    count = 0
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)  # noqa: S603 - command is constructed internally, not from user input
    try:
        assert process.stdout is not None  # noqa: S101 - type narrowing for Popen(stdout=PIPE)
        # A blocking `for line in process.stdout` cannot be interrupted, so a backend that hangs
        # without output would ignore stop requests. Read on a side thread and poll a queue instead.
        lines: queue.Queue[str | None] = queue.Queue()
        reader = threading.Thread(target=_read_lines, args=(process.stdout, lines), daemon=True)
        reader.start()
        idle = 0.0
        while not (is_interrupted() or count >= MAX_RESULTS):
            try:
                line = lines.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                idle += _POLL_INTERVAL
                if idle >= _IDLE_TIMEOUT:
                    break
                continue
            idle = 0.0
            if line is None:
                break
            path = line.rstrip("\r\n")
            if not path:
                continue
            file_path = Path(path)
            name = file_path.name
            name_lower = name.lower()
            if not _matches(name_lower, normalized_query, tokens):
                continue
            parts = file_path.parts
            if SKIP_DIRS.intersection(parts):
                continue
            is_dir = file_path.is_dir()
            depth = len(parts) - 1
            on_found(path, _score(normalized_query, name), depth, is_dir)
            count += 1
    finally:
        process.terminate()
        process.wait()
    return count
