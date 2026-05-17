from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

import seekbar.search
from seekbar.search import SearchWorker, discover_roots

# _score is module-level, not a class internal; tests must verify it directly
# noinspection PyProtectedMember
_score = seekbar.search._score

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class _FakeScandir:
    def __init__(self, entries):
        self._entries = entries

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def __iter__(self):
        return iter(self._entries)


class TestScore:
    @pytest.mark.parametrize(
        ("query", "name", "expected"),
        [
            pytest.param("hosts", "hosts", 0, id="exact"),
            pytest.param("hosts", "HOSTS", 0, id="exact-case-insensitive"),
            pytest.param("hosts", "hosts.txt", 1, id="stem-match"),
            pytest.param("hosts", "hosts.bak", 1, id="stem-alt-extension"),
            pytest.param("hosts", "hostsfile", 2, id="starts-with"),
            pytest.param("hosts", "hosts.txt.bak", 2, id="starts-with-double-ext"),
            pytest.param("hosts", "myhosts", 3, id="ends-with"),
            pytest.param("hosts", "xhostsy", 4, id="contains-middle"),
            pytest.param("hosts", "myhosts.log", 4, id="contains-with-ext"),
        ],
    )
    def test_score_levels(self, query: str, name: str, expected: int):
        assert _score(query, name) == expected

    def test_stem_match_uses_last_dot(self):
        assert _score("hosts.txt", "hosts.txt.bak") == 1

    def test_no_extension_exact_match(self):
        assert _score("makefile", "Makefile") == 0


class TestDiscoverRoots:
    def test_returns_nonempty_list(self):
        roots = discover_roots()
        assert len(roots) > 0
        assert all(isinstance(r, Path) for r in roots)

    def test_all_roots_exist(self):
        assert all(r.exists() for r in discover_roots())

    def test_windows_includes_c_drive(self):
        if platform.system() != "Windows":
            pytest.skip("Windows-only")
        assert Path("C:\\") in discover_roots()

    def test_unknown_platform_returns_root(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "UnknownOS")
        with pytest.warns(UserWarning, match="Unsupported platform"):
            roots = discover_roots()
        assert roots == [Path("/")]

    def test_darwin_without_volumes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        mock_volumes = MagicMock()
        mock_volumes.is_dir.return_value = False

        original_path = Path

        def fake_path(arg):
            if arg == "/Volumes":
                return mock_volumes
            return original_path(arg)

        monkeypatch.setattr(seekbar.search, "Path", fake_path)
        roots = discover_roots()
        assert len(roots) == 1

    def test_darwin_with_volumes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        mock_usb = MagicMock()
        mock_usb.is_dir.return_value = True
        mock_file = MagicMock()
        mock_file.is_dir.return_value = False
        mock_volumes = MagicMock()
        mock_volumes.is_dir.return_value = True
        mock_volumes.iterdir.return_value = [mock_usb, mock_file]

        original_path = Path

        def fake_path(arg):
            if arg == "/Volumes":
                return mock_volumes
            return original_path(arg)

        monkeypatch.setattr(seekbar.search, "Path", fake_path)
        roots = discover_roots()
        assert len(roots) == 2
        assert mock_usb in roots

    def test_linux_without_mounts(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        mock_mnt = MagicMock()
        mock_mnt.is_dir.return_value = False
        mock_media = MagicMock()
        mock_media.is_dir.return_value = False

        original_path = Path
        path_map = {"/mnt": mock_mnt, "/media": mock_media}

        def fake_path(arg):
            if arg in path_map:
                return path_map[arg]
            return original_path(arg)

        monkeypatch.setattr(seekbar.search, "Path", fake_path)
        roots = discover_roots()
        assert len(roots) == 1

    def test_linux_with_mounts(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        mock_usb = MagicMock()
        mock_usb.is_dir.return_value = True
        mock_mnt = MagicMock()
        mock_mnt.is_dir.return_value = True
        mock_mnt.iterdir.return_value = [mock_usb]
        mock_media = MagicMock()
        mock_media.is_dir.return_value = False

        original_path = Path
        path_map = {"/mnt": mock_mnt, "/media": mock_media}

        def fake_path(arg):
            if arg in path_map:
                return path_map[arg]
            return original_path(arg)

        monkeypatch.setattr(seekbar.search, "Path", fake_path)
        roots = discover_roots()
        assert len(roots) == 2
        assert mock_usb in roots


class TestSearchWorker:
    @pytest.fixture
    def search_tree(self, tmp_path: Path) -> Path:
        (tmp_path / "hosts").touch()
        (tmp_path / "hosts.txt").write_text("data")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "myhosts").touch()
        (sub / "readme.txt").write_text("data")
        return tmp_path

    def test_finds_matching_files(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.found.connect(lambda p, _s: results.append(Path(p).name))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert sorted(results) == ["hosts", "hosts.txt", "myhosts"]

    def test_excludes_non_matching(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.found.connect(lambda p, _s: results.append(Path(p).name))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert "readme.txt" not in results

    def test_emits_correct_scores(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        scores: dict[str, int] = {}

        def on_found(path: str, score: int):
            scores[Path(path).name] = score

        worker.found.connect(on_found)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert scores["hosts"] == 0
        assert scores["hosts.txt"] == 1
        assert scores["myhosts"] == 3

    def test_finished_emits_total(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")

        with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
            worker.start()

        assert blocker.args == [3]

    @pytest.mark.usefixtures("qtbot")
    def test_stop_interrupts(self, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        worker.start()
        worker.stop()
        assert worker.wait(3000)

    def test_max_results_limit(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        for i in range(10):
            (tmp_path / f"hosts_{i}").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 3)

        worker = SearchWorker("hosts")
        count: list[int] = []
        worker.found.connect(lambda _p, _s: count.append(1))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert len(count) == 3

    def test_max_results_stops_across_roots(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root1 = tmp_path / "root1"
        root1.mkdir()
        root2 = tmp_path / "root2"
        root2.mkdir()
        for i in range(5):
            (root1 / f"hosts_{i}").touch()
        (root2 / "hosts_extra").touch()

        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [root1, root2])
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 3)

        worker = SearchWorker("hosts")
        count: list[int] = []
        worker.found.connect(lambda _p, _s: count.append(1))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert len(count) == 3

    def test_scandir_permission_error(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr(os, "scandir", MagicMock(side_effect=PermissionError))

        worker = SearchWorker("anything")
        with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
            worker.start()

        assert blocker.args == [0]

    def test_is_dir_os_error(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])

        entry = MagicMock()
        entry.name = "hosts_file"
        entry.path = str(tmp_path / "hosts_file")
        entry.is_dir.side_effect = OSError("Simulated")

        monkeypatch.setattr(os, "scandir", lambda _path: _FakeScandir([entry]))

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.found.connect(lambda p, _s: results.append(p))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert len(results) == 1
