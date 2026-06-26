import bisect
import json
from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QSettings, Qt

from seekbar.constants import _IS_DIR_ROLE, _NAME_ROLE, _PARENT_ROLE, SETTINGS_APP, SETTINGS_ORG

if TYPE_CHECKING:
    from PySide6.QtCore import QPersistentModelIndex


_NO_PARENT = QModelIndex()


class _RecencyStore:
    """Persists recently opened paths (most-recent-first) so repeat results rank higher."""

    _LIMIT = 500
    _KEY = "recent_paths"

    def __init__(self) -> None:
        self._paths = self._load()
        self._ranks = {path: index for index, path in enumerate(self._paths)}

    @classmethod
    def _load(cls) -> list[str]:
        raw = QSettings(SETTINGS_ORG, SETTINGS_APP).value(cls._KEY, "[]")
        if not isinstance(raw, str):
            return []
        try:
            stored = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(stored, list):
            return []
        return [path for path in stored if isinstance(path, str)]

    def rank(self, path: str) -> int:
        return self._ranks.get(path, self._LIMIT)

    def record(self, path: str) -> None:
        if self._paths[:1] == [path]:
            return
        if path in self._ranks:
            self._paths.remove(path)
        self._paths.insert(0, path)
        del self._paths[self._LIMIT :]
        self._ranks = {stored: index for index, stored in enumerate(self._paths)}
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(self._KEY, json.dumps(self._paths))


def _basename_length(path: str) -> int:
    # Length of the final path component without allocating a Path; handles either separator.
    return len(path) - max(path.rfind("\\"), path.rfind("/")) - 1


class _ResultModel(QAbstractListModel):
    def __init__(self, recency: _RecencyStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._recency = recency
        self._keys: list[tuple[int, int, int, int]] = []
        self._rows: list[tuple[str, bool, str, str]] = []

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _NO_PARENT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return row[0]
        if role == _IS_DIR_ROLE:
            return row[1]
        if role == _NAME_ROLE:
            return row[2]
        if role == _PARENT_ROLE:
            return row[3]
        return None

    def add_batch(self, results: list[tuple[str, int, int, bool]]) -> None:
        if not results:
            return
        # Build (key, row) once per result; name/parent are precomputed here so paint never parses
        # a Path. Recency breaks ties within a score tier; basename length is the final tiebreaker.
        items: list[tuple[tuple[int, int, int, int], tuple[str, bool, str, str]]] = []
        for path, score, depth, is_dir in results:
            key = (score, self._recency.rank(path), depth, _basename_length(path))
            file_path = Path(path)
            items.append((key, (path, is_dir, file_path.name, file_path.parent.name or str(file_path.parent))))
        items.sort(key=lambda item: item[0])

        keys = self._keys
        rows = self._rows
        # Merge the sorted batch into the sorted model, splicing each maximal run of batch items
        # that share one insertion point in a single beginInsertRows span. `lo` is a monotonically
        # rising lower bound: every later batch key inserts at or after the previous run's tail.
        lo = 0
        index = 0
        count = len(items)
        while index < count:
            pos = bisect.bisect_right(keys, items[index][0], lo)
            run_start = index
            if pos < len(keys):
                limit = keys[pos]  # first existing key strictly greater than the batch key
                index += 1
                while index < count and items[index][0] < limit:
                    index += 1
            else:
                index = count  # no existing tail: all remaining (sorted) batch items append here
            run = items[run_start:index]
            self.beginInsertRows(_NO_PARENT, pos, pos + len(run) - 1)
            keys[pos:pos] = [item[0] for item in run]
            rows[pos:pos] = [item[1] for item in run]
            self.endInsertRows()
            lo = pos + len(run)

    def clear(self) -> None:
        self.beginResetModel()
        self._keys.clear()
        self._rows.clear()
        self.endResetModel()

    def path_at(self, row: int) -> str:
        return self._rows[row][0]
