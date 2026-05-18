from __future__ import annotations

import os
import platform
import string
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from collections.abc import Callable

    from seekbar._mft import MftRecord

MAX_RESULTS = 10_000

SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".venv",
    "venv",
    "$RECYCLE.BIN",
    "System Volume Information",
    ".Trash",
    ".Spotlight-V100",
    ".fseventsd",
})


def _score(query: str, name: str) -> int:
    lowercase_name = name.lower()
    if lowercase_name == query:
        return 0
    stem = lowercase_name.rsplit(".", maxsplit=1)[0] if "." in lowercase_name else lowercase_name
    if stem == query:
        return 1
    if lowercase_name.startswith(query):
        return 2
    if lowercase_name.endswith(query):
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
            mount_dir = Path("/mnt")
            media = Path("/media")
            for parent in (mount_dir, media):
                if parent.is_dir():
                    roots.extend(p for p in parent.iterdir() if p.is_dir())
            return roots
        case other:
            warnings.warn(f"Unsupported platform: {other}", stacklevel=2)
            return [Path("/")]


class WalkSearchStrategy:
    def __init__(self, roots: list[Path]) -> None:
        self._roots = roots

    def execute(
        self,
        query: str,
        on_found: Callable[[str, int, int, bool], object],
        is_interrupted: Callable[[], bool],
    ) -> int:
        count = 0
        for root in self._roots:
            if is_interrupted() or count >= MAX_RESULTS:
                return count
            count += self._walk(root, query, on_found, is_interrupted, count)
        return count

    @staticmethod
    def _walk(
        root: Path,
        query: str,
        on_found: Callable[[str, int, int, bool], object],
        is_interrupted: Callable[[], bool],
        initial_count: int,
    ) -> int:
        count = 0
        stack: list[str] = [str(root)]
        while stack:
            if is_interrupted() or (initial_count + count) >= MAX_RESULTS:
                return count
            current = stack.pop()
            try:
                entries = os.scandir(current)
            except OSError:
                continue
            with entries:
                for entry in entries:
                    if is_interrupted() or (initial_count + count) >= MAX_RESULTS:
                        return count
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        is_dir = False
                    if query in entry.name.lower():
                        depth = entry.path.count(os.sep)
                        on_found(entry.path, _score(query, entry.name), depth, is_dir)
                        count += 1
                    if is_dir and entry.name not in SKIP_DIRS:
                        stack.append(entry.path)
        return count


class MftSearchStrategy:
    def __init__(self, drive_letter: str) -> None:
        self._drive = drive_letter.rstrip("\\")
        self._records: dict[int, tuple[int, str, bool]] = {}
        self._path_cache: dict[int, str] = {}
        self._skip_refs: set[int] = set()
        self._pending: dict[int, MftRecord] = {}
        self._count = 0

    def execute(
        self,
        query: str,
        on_found: Callable[[str, int, int, bool], object],
        is_interrupted: Callable[[], bool],
    ) -> int:
        from seekbar._mft import stream_mft  # noqa: PLC0415 - conditional, _mft is Windows-only

        for batch in stream_mft(self._drive):
            if is_interrupted() or self._count >= MAX_RESULTS:
                break
            self._ingest_batch(batch)
            self._match_batch(batch, query, on_found)
            self._retry_pending(query, on_found)

        self._sweep_pending(query, on_found)
        return self._count

    def _ingest_batch(self, batch: list[MftRecord]) -> None:
        for mft_record in batch:
            self._records[mft_record.file_ref] = (mft_record.parent_ref, mft_record.name, mft_record.is_dir)
            if mft_record.is_dir and mft_record.name in SKIP_DIRS:
                self._skip_refs.add(mft_record.file_ref)

    def _match_batch(
        self, batch: list[MftRecord], query: str, on_found: Callable[[str, int, int, bool], object],
    ) -> None:
        from seekbar._mft import _MFT_ROOT_REF, resolve_path  # noqa: PLC0415 - conditional, _mft is Windows-only

        for mft_record in batch:
            if self._count >= MAX_RESULTS:
                return
            if query not in mft_record.name.lower():
                continue
            resolved = resolve_path(mft_record.file_ref, self._records, _MFT_ROOT_REF, self._drive, self._path_cache)
            if resolved:
                if not self._is_under_skip_dir(mft_record.file_ref):
                    on_found(resolved, _score(query, mft_record.name), resolved.count("\\"), mft_record.is_dir)
                    self._count += 1
            else:
                self._pending[mft_record.file_ref] = mft_record

    def _retry_pending(self, query: str, on_found: Callable[[str, int, int, bool], object]) -> None:
        from seekbar._mft import _MFT_ROOT_REF, resolve_path  # noqa: PLC0415 - conditional, _mft is Windows-only

        resolved_refs: list[int] = []
        for ref, mft_record in self._pending.items():
            if self._count >= MAX_RESULTS:
                break
            resolved = resolve_path(ref, self._records, _MFT_ROOT_REF, self._drive, self._path_cache)
            if resolved:
                resolved_refs.append(ref)
                if not self._is_under_skip_dir(ref):
                    on_found(resolved, _score(query, mft_record.name), resolved.count("\\"), mft_record.is_dir)
                    self._count += 1
        for ref in resolved_refs:
            del self._pending[ref]

    def _sweep_pending(self, query: str, on_found: Callable[[str, int, int, bool], object]) -> None:
        from seekbar._mft import _MFT_ROOT_REF, resolve_path  # noqa: PLC0415 - conditional, _mft is Windows-only

        for ref, mft_record in self._pending.items():
            if self._count >= MAX_RESULTS:
                break
            resolved = resolve_path(ref, self._records, _MFT_ROOT_REF, self._drive, self._path_cache)
            if resolved and not self._is_under_skip_dir(ref):
                on_found(resolved, _score(query, mft_record.name), resolved.count("\\"), mft_record.is_dir)
                self._count += 1

    def _is_under_skip_dir(self, file_ref: int) -> bool:
        from seekbar._mft import _MFT_ROOT_REF  # noqa: PLC0415 - conditional, _mft is Windows-only

        current = file_ref
        seen: set[int] = set()
        while current in self._records and current != _MFT_ROOT_REF:
            if current in self._skip_refs:
                return True
            if current in seen:
                return False
            seen.add(current)
            current = self._records[current][0]
        return False


class SearchWorker(QThread):
    found = Signal(str, int, int, bool)
    finished = Signal(int)

    def __init__(self, query: str) -> None:
        super().__init__()
        self._query = query.lower()
        self._count = 0

    def run(self) -> None:
        roots = discover_roots()
        if sys.platform == "win32":
            self._run_with_mft_fallback(roots)
        else:
            self._run_walk(roots)
        self.finished.emit(self._count)

    def _run_with_mft_fallback(self, roots: list[Path]) -> None:
        from seekbar._mft import is_ntfs  # noqa: PLC0415 - conditional, _mft is Windows-only

        for root in roots:
            if self.isInterruptionRequested() or self._count >= MAX_RESULTS:
                return
            drive = str(root).rstrip("\\")
            if is_ntfs(drive):
                try:
                    self._count += MftSearchStrategy(drive).execute(
                        self._query, self.found.emit, self.isInterruptionRequested,
                    )
                    continue
                except OSError:
                    pass
            self._count += WalkSearchStrategy([root]).execute(
                self._query, self.found.emit, self.isInterruptionRequested,
            )

    def _run_walk(self, roots: list[Path]) -> None:
        self._count += WalkSearchStrategy(roots).execute(
            self._query, self.found.emit, self.isInterruptionRequested,
        )

    def stop(self) -> None:
        self.requestInterruption()
