import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from seekbar.search import MAX_RESULTS, SKIP_DIRS, _matches, _score

if TYPE_CHECKING:
    from collections.abc import Callable


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
        for line in process.stdout:
            if is_interrupted() or count >= MAX_RESULTS:
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
