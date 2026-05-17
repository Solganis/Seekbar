from __future__ import annotations

import os
import platform
import string
import warnings
from pathlib import Path

from PySide6.QtCore import QThread, Signal

MAX_RESULTS = 10_000


def _score(query: str, name: str) -> int:
    low = name.lower()
    if low == query:
        return 0
    stem = low.rsplit(".", maxsplit=1)[0] if "." in low else low
    if stem == query:
        return 1
    if low.startswith(query):
        return 2
    if low.endswith(query):
        return 3
    return 4


def discover_roots() -> list[Path]:
    match platform.system():
        case "Windows":
            return [Path(f"{letter}:\\") for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
        case "Darwin":
            roots = [Path("/")]
            volumes = Path("/Volumes")
            if volumes.is_dir():
                roots.extend(p for p in volumes.iterdir() if p.is_dir())
            return roots
        case "Linux":
            roots = [Path("/")]
            mnt = Path("/mnt")
            media = Path("/media")
            for parent in (mnt, media):
                if parent.is_dir():
                    roots.extend(p for p in parent.iterdir() if p.is_dir())
            return roots
        case other:
            warnings.warn(f"Unsupported platform: {other}", stacklevel=2)
            return [Path("/")]


class SearchWorker(QThread):
    found = Signal(str, int)
    finished = Signal(int)

    def __init__(self, query: str) -> None:
        super().__init__()
        self._query = query.lower()
        self._count = 0

    def run(self) -> None:
        roots = discover_roots()
        for root in roots:
            if self.isInterruptionRequested():
                break
            self._walk(root)
        self.finished.emit(self._count)

    def _walk(self, directory: Path) -> None:
        if self.isInterruptionRequested() or self._count >= MAX_RESULTS:
            return
        try:
            entries = os.scandir(directory)
        except PermissionError, OSError:
            return
        with entries:
            for entry in entries:
                if self.isInterruptionRequested() or self._count >= MAX_RESULTS:
                    return
                if self._query in entry.name.lower():
                    self.found.emit(entry.path, _score(self._query, entry.name))
                    self._count += 1
                try:
                    if entry.is_dir(follow_symlinks=False):
                        self._walk(Path(entry.path))
                except PermissionError, OSError:
                    continue

    def stop(self) -> None:
        self.requestInterruption()
