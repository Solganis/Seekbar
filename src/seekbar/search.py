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
        self._buffer: list[tuple[str, int, int, bool]] = []

    def _buffer_result(self, path: str, score: int, depth: int, is_dir: bool) -> None:  # noqa: FBT001 - matches strategy callback signature
        self._buffer.append((path, score, depth, is_dir))
        if len(self._buffer) >= _BATCH_SIZE:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        if self._buffer:
            self.batch_found.emit(self._buffer.copy())
            self._buffer.clear()

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

    def _run_with_mft_fallback(self, roots: list[Path]) -> None:
        from seekbar._mft import is_ntfs  # noqa: PLC0415 - conditional, _mft is Windows-only

        for root in roots:
            if self.isInterruptionRequested() or self._count >= MAX_RESULTS:
                return
            drive = str(root).rstrip("\\")
            if is_ntfs(drive):
                try:
                    self._count += MftSearchStrategy(drive).execute(
                        self._normalized_query,
                        self._tokens,
                        self._buffer_result,
                        self.isInterruptionRequested,
                    )
                    continue
                except OSError:
                    pass
            self._count += WalkSearchStrategy([root]).execute(
                self._normalized_query,
                self._tokens,
                self._buffer_result,
                self.isInterruptionRequested,
            )

    def _run_with_spotlight_fallback(self, roots: list[Path]) -> None:
        import shutil  # noqa: PLC0415 - conditional platform import

        # noinspection PyDeprecation
        if shutil.which("mdfind"):
            from seekbar._spotlight import SpotlightSearchStrategy  # noqa: PLC0415 - conditional platform import

            try:
                self._count += SpotlightSearchStrategy().execute(
                    self._normalized_query,
                    self._tokens,
                    self._buffer_result,
                    self.isInterruptionRequested,
                )
            except OSError:
                pass
            else:
                return
        self._run_walk(roots)

    def _run_with_locate_fallback(self, roots: list[Path]) -> None:
        import shutil  # noqa: PLC0415 - conditional platform import

        # noinspection PyDeprecation
        command = shutil.which("plocate") or shutil.which("locate")
        if command:
            from seekbar._locate import LocateSearchStrategy  # noqa: PLC0415 - conditional platform import

            try:
                self._count += LocateSearchStrategy(command).execute(
                    self._normalized_query,
                    self._tokens,
                    self._buffer_result,
                    self.isInterruptionRequested,
                )
            except OSError:
                pass
            else:
                return
        self._run_walk(roots)

    def _run_walk(self, roots: list[Path]) -> None:
        self._count += WalkSearchStrategy(roots).execute(
            self._normalized_query,
            self._tokens,
            self._buffer_result,
            self.isInterruptionRequested,
        )

    def stop(self) -> None:
        self.requestInterruption()
