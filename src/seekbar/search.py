import os
import platform
import string
import sys
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from collections.abc import Callable

    from seekbar._mft import MftRecord

MAX_RESULTS = 10_000
_BATCH_SIZE = 100

SKIP_DIRS: frozenset[str] = frozenset(
    {
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
    }
)

_SEPARATORS = str.maketrans("_-", "  ")


def _normalize(text: str) -> str:
    if "_" not in text and "-" not in text:
        return text
    return text.translate(_SEPARATORS)


def _matches_normalized(normalized_name: str, normalized_query: str, tokens: list[str]) -> bool:
    if normalized_query in normalized_name:
        return True
    return len(tokens) > 1 and all(token in normalized_name for token in tokens)


def _matches(name_lower: str, normalized_query: str, tokens: list[str]) -> bool:
    return _matches_normalized(_normalize(name_lower), normalized_query, tokens)


def _score_from_normalized(normalized_query: str, normalized_name: str) -> int:
    if normalized_query not in normalized_name:
        return 5
    if normalized_name == normalized_query:
        return 0
    stem = normalized_name.rsplit(".", maxsplit=1)[0] if "." in normalized_name else normalized_name
    if stem == normalized_query:
        return 1
    if normalized_name.startswith(normalized_query):
        return 2
    if normalized_name.endswith(normalized_query):
        return 3
    return 4


def _score(normalized_query: str, name: str) -> int:
    return _score_from_normalized(normalized_query, _normalize(name.lower()))


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
        normalized_query: str,
        tokens: list[str],
        on_found: Callable[[str, int, int, bool], object],
        is_interrupted: Callable[[], bool],
    ) -> int:
        count = 0
        for root in self._roots:
            if is_interrupted() or count >= MAX_RESULTS:
                return count
            count += self._walk(root, normalized_query, tokens, on_found, is_interrupted, count)
        return count

    @staticmethod
    def _walk(  # noqa: PLR0913 - tightly coupled walk parameters
        root: Path,
        normalized_query: str,
        tokens: list[str],
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
                    normalized_name = _normalize(entry.name.lower())
                    if _matches_normalized(normalized_name, normalized_query, tokens):
                        depth = entry.path.count(os.sep)
                        on_found(entry.path, _score_from_normalized(normalized_query, normalized_name), depth, is_dir)
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
        self._skip_cache: dict[int, bool] = {}
        self._pending: dict[int, MftRecord] = {}
        self._count = 0

    def execute(
        self,
        normalized_query: str,
        tokens: list[str],
        on_found: Callable[[str, int, int, bool], object],
        is_interrupted: Callable[[], bool],
    ) -> int:
        from seekbar._mft import stream_mft  # noqa: PLC0415 - conditional, _mft is Windows-only

        for batch in stream_mft(self._drive):
            if is_interrupted() or self._count >= MAX_RESULTS:
                break
            self._process_batch(batch, normalized_query, tokens, on_found)
            self._resolve_pending(normalized_query, on_found, cleanup=True)

        self._resolve_pending(normalized_query, on_found, cleanup=False)
        return self._count

    def _process_batch(
        self,
        batch: list[MftRecord],
        normalized_query: str,
        tokens: list[str],
        on_found: Callable[[str, int, int, bool], object],
    ) -> None:
        from seekbar._mft import _MFT_ROOT_REF, resolve_path  # noqa: PLC0415 - conditional, _mft is Windows-only

        records = self._records
        skip_refs = self._skip_refs
        path_cache = self._path_cache
        pending = self._pending
        drive = self._drive
        count = self._count
        for mft_record in batch:
            file_ref = mft_record.file_ref
            name = mft_record.name
            is_dir = mft_record.is_dir
            records[file_ref] = (mft_record.parent_ref, name, is_dir)
            if is_dir and name in SKIP_DIRS:
                skip_refs.add(file_ref)
            if count >= MAX_RESULTS:
                continue
            normalized_name = _normalize(name.lower())
            if not _matches_normalized(normalized_name, normalized_query, tokens):
                continue
            resolved = resolve_path(file_ref, records, _MFT_ROOT_REF, drive, path_cache)
            if not resolved:
                pending[file_ref] = mft_record
                continue
            if not self._is_under_skip_dir(file_ref):
                score = _score_from_normalized(normalized_query, normalized_name)
                on_found(resolved, score, resolved.count("\\"), is_dir)
                count += 1
        self._count = count

    def _resolve_pending(
        self,
        normalized_query: str,
        on_found: Callable[[str, int, int, bool], object],
        *,
        cleanup: bool,
    ) -> None:
        from seekbar._mft import _MFT_ROOT_REF, resolve_path  # noqa: PLC0415 - conditional, _mft is Windows-only

        records = self._records
        path_cache = self._path_cache
        pending = self._pending
        drive = self._drive
        resolved_refs: list[int] = []
        for ref, mft_record in pending.items():
            if self._count >= MAX_RESULTS:
                break
            resolved = resolve_path(ref, records, _MFT_ROOT_REF, drive, path_cache)
            if resolved:
                resolved_refs.append(ref)
                if not self._is_under_skip_dir(ref):
                    score = _score(normalized_query, mft_record.name)
                    on_found(resolved, score, resolved.count("\\"), mft_record.is_dir)
                    self._count += 1
        if cleanup:
            for ref in resolved_refs:
                del pending[ref]

    def _is_under_skip_dir(self, file_ref: int) -> bool:
        from seekbar._mft import _MFT_ROOT_REF  # noqa: PLC0415 - conditional, _mft is Windows-only

        records = self._records
        skip_refs = self._skip_refs
        skip_cache = self._skip_cache
        chain: list[int] = []
        current = file_ref
        seen: set[int] = set()
        result = False
        while current in records and current != _MFT_ROOT_REF:
            if current in skip_cache:
                result = skip_cache[current]
                break
            if current in skip_refs:
                result = True
                break
            if current in seen:
                break
            seen.add(current)
            chain.append(current)
            current = records[current][0]
        for ref in chain:
            skip_cache[ref] = result
        return result


class SearchWorker(QThread):
    batch_found = Signal(list)
    finished = Signal(int)

    def __init__(self, query: str) -> None:
        super().__init__()
        self._normalized_query = _normalize(query.lower())
        self._tokens = self._normalized_query.split()
        self._count = 0
        self._emitted = 0
        self._buffer: list[tuple[str, int, int, bool]] = []
        self._lock = threading.Lock()

    def _buffer_result(self, path: str, score: int, depth: int, is_dir: bool) -> None:  # noqa: FBT001 - matches strategy callback signature
        with self._lock:
            if self._emitted >= MAX_RESULTS:
                return
            self._buffer.append((path, score, depth, is_dir))
            self._emitted += 1
            if len(self._buffer) >= _BATCH_SIZE:
                self.batch_found.emit(self._buffer.copy())
                self._buffer.clear()

    def _flush_buffer(self) -> None:
        with self._lock:
            if self._buffer:
                self.batch_found.emit(self._buffer.copy())
                self._buffer.clear()

    def _stop_requested(self) -> bool:
        return self.isInterruptionRequested() or self._emitted >= MAX_RESULTS

    def run(self) -> None:
        roots = discover_roots()
        match sys.platform:
            case "win32":
                self._run_with_mft_fallback(roots)
            case "darwin":
                self._run_with_spotlight_fallback(roots)
            case "linux":
                self._run_with_locate_fallback(roots)
            case _:
                self._run_walk(roots)
        self._flush_buffer()
        self.finished.emit(self._count)

    def _search_roots_parallel(self, roots: list[Path], search_one: Callable[[Path], int]) -> None:
        if len(roots) == 1:
            self._count += search_one(roots[0])
            return
        with ThreadPoolExecutor(max_workers=len(roots)) as executor:
            for found in executor.map(search_one, roots):
                self._count += found

    def _run_with_mft_fallback(self, roots: list[Path]) -> None:
        self._search_roots_parallel(roots, self._search_root_mft)

    def _search_root_mft(self, root: Path) -> int:
        from seekbar._mft import is_ntfs  # noqa: PLC0415 - conditional, _mft is Windows-only

        drive = str(root).rstrip("\\")
        if is_ntfs(drive):
            try:
                return MftSearchStrategy(drive).execute(
                    self._normalized_query,
                    self._tokens,
                    self._buffer_result,
                    self._stop_requested,
                )
            except OSError:
                pass
        return WalkSearchStrategy([root]).execute(
            self._normalized_query,
            self._tokens,
            self._buffer_result,
            self._stop_requested,
        )

    def _run_with_spotlight_fallback(self, roots: list[Path]) -> None:
        import shutil  # noqa: PLC0415 - conditional platform import

        # str arg hits the non-deprecated which(str) overload; the PathLike/Windows<3.12 note is moot here
        # noinspection PyDeprecation
        if shutil.which("mdfind"):
            from seekbar._spotlight import SpotlightSearchStrategy  # noqa: PLC0415 - conditional platform import

            try:
                self._count += SpotlightSearchStrategy().execute(
                    self._normalized_query,
                    self._tokens,
                    self._buffer_result,
                    self._stop_requested,
                )
            except OSError:
                pass
            else:
                return
        self._run_walk(roots)

    def _run_with_locate_fallback(self, roots: list[Path]) -> None:
        import shutil  # noqa: PLC0415 - conditional platform import

        # str args hit the non-deprecated which(str) overload; the PathLike/Windows<3.12 note is moot here
        # noinspection PyDeprecation
        command = shutil.which("plocate") or shutil.which("locate")
        if command:
            from seekbar._locate import LocateSearchStrategy  # noqa: PLC0415 - conditional platform import

            try:
                self._count += LocateSearchStrategy(command).execute(
                    self._normalized_query,
                    self._tokens,
                    self._buffer_result,
                    self._stop_requested,
                )
            except OSError:
                pass
            else:
                return
        self._run_walk(roots)

    def _run_walk(self, roots: list[Path]) -> None:
        self._search_roots_parallel(roots, self._walk_root)

    def _walk_root(self, root: Path) -> int:
        return WalkSearchStrategy([root]).execute(
            self._normalized_query,
            self._tokens,
            self._buffer_result,
            self._stop_requested,
        )

    def stop(self) -> None:
        self.requestInterruption()
