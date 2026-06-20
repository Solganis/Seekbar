import os
import platform
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from assertpy2 import assert_that

import seekbar.search
from seekbar.search import (
    MAX_RESULTS,
    SKIP_DIRS,
    SearchWorker,
    WalkSearchStrategy,
    discover_roots,
)

if sys.platform == "win32":
    # noinspection PyProtectedMember
    from seekbar._mft import MftRecord
    from seekbar.search import MftSearchStrategy


# noinspection PyProtectedMember
_score = seekbar.search._score
# noinspection PyProtectedMember
_matches = seekbar.search._matches
# noinspection PyProtectedMember
_normalize = seekbar.search._normalize

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


class TestNormalize:
    def test_underscore_to_space(self):
        assert_that(_normalize("hello_world")).is_equal_to("hello world")

    def test_hyphen_to_space(self):
        assert_that(_normalize("hello-world")).is_equal_to("hello world")

    def test_mixed_separators(self):
        assert_that(_normalize("my_file-name")).is_equal_to("my file name")

    def test_no_separators(self):
        assert_that(_normalize("helloworld")).is_equal_to("helloworld")

    def test_empty_string(self):
        assert_that(_normalize("")).is_empty()


class TestMatches:
    def test_exact_substring(self):
        assert_that(_matches("hello_world", "hello world", ["hello", "world"])).is_true()

    def test_no_match(self):
        assert_that(_matches("foobar", "hello world", ["hello", "world"])).is_false()

    def test_token_only_different_order(self):
        assert_that(_matches("world_hello", "hello world", ["hello", "world"])).is_true()

    def test_single_token_substring_match(self):
        assert_that(_matches("worldhello", "hello", ["hello"])).is_true()

    def test_single_token_no_match(self):
        assert_that(_matches("foobar", "hello", ["hello"])).is_false()

    def test_single_token_substring(self):
        assert_that(_matches("say_hello_there", "hello", ["hello"])).is_true()

    def test_hyphen_matches_underscore_query(self):
        assert_that(_matches("hello-world", "hello world", ["hello", "world"])).is_true()

    def test_concatenated_tokens_match(self):
        assert_that(_matches("helloworld", "hello world", ["hello", "world"])).is_true()

    def test_tokens_scattered_in_name(self):
        assert_that(_matches("my_hello_big_world", "hello world", ["hello", "world"])).is_true()


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
        assert_that(_score(query, name)).is_equal_to(expected)

    def test_stem_match_uses_last_dot(self):
        assert_that(_score("hosts.txt", "hosts.txt.bak")).is_equal_to(1)

    def test_no_extension_exact_match(self):
        assert_that(_score("makefile", "Makefile")).is_equal_to(0)

    def test_normalized_exact_match(self):
        assert_that(_score("hello world", "hello_world")).is_equal_to(0)

    def test_normalized_stem_match(self):
        assert_that(_score("hello world", "hello_world.txt")).is_equal_to(1)

    def test_normalized_starts_with(self):
        assert_that(_score("hello world", "hello_world_extra")).is_equal_to(2)

    def test_normalized_ends_with(self):
        assert_that(_score("hello world", "my_hello_world")).is_equal_to(3)

    def test_normalized_contains(self):
        assert_that(_score("hello world", "my_hello_world_file.txt")).is_equal_to(4)

    def test_token_only_score(self):
        assert_that(_score("hello world", "world_hello")).is_equal_to(5)


class TestDiscoverRoots:
    def test_returns_nonempty_list(self):
        roots = discover_roots()
        assert_that(roots).is_not_empty()
        assert_that(roots).all_satisfy(lambda root: isinstance(root, Path))

    def test_all_roots_exist(self):
        assert_that(discover_roots()).all_satisfy(lambda root: root.exists())

    def test_windows_includes_c_drive(self):
        if platform.system() != "Windows":
            pytest.skip("Windows-only")
        assert_that(discover_roots()).contains(Path("C:\\"))

    def test_unknown_platform_returns_root(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "UnknownOS")
        with pytest.warns(UserWarning, match="Unsupported platform"):
            roots = discover_roots()
        assert_that(roots).is_equal_to([Path("/")])

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
        assert_that(roots).is_length(1)

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
        assert_that(roots).is_length(2)
        assert_that(roots).contains(mock_usb)

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
        assert_that(roots).is_length(1)

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
        assert_that(roots).is_length(2)
        assert_that(roots).contains(mock_usb)


class TestSearchWorker:
    @pytest.fixture
    def search_tree(self, tmp_path: Path) -> Path:
        (tmp_path / "hosts").touch()
        (tmp_path / "hosts.txt").write_text("data")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "myhosts").touch()
        (subdir / "readme.txt").write_text("data")
        return tmp_path

    def test_finds_matching_files(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(sorted(results)).is_equal_to(["hosts", "hosts.txt", "myhosts"])

    def test_excludes_non_matching(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(results).does_not_contain("readme.txt")

    def test_emits_correct_scores(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        scores: dict[str, int] = {}

        def on_batch(batch: list[tuple[str, int, int, bool]]):
            for path, score, _depth, _is_dir in batch:
                scores[Path(path).name] = score

        worker.batch_found.connect(on_batch)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(scores["hosts"]).is_equal_to(0)
        assert_that(scores["hosts.txt"]).is_equal_to(1)
        assert_that(scores["myhosts"]).is_equal_to(3)

    def test_emits_depth(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        depths: dict[str, int] = {}

        def on_batch(batch: list[tuple[str, int, int, bool]]):
            for path, _s, depth, _is_dir in batch:
                depths[Path(path).name] = depth

        worker.batch_found.connect(on_batch)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        top_level_depth = depths["hosts"]
        sub_depth = depths["myhosts"]
        assert_that(sub_depth).is_greater_than(top_level_depth)

    def test_finished_emits_total(self, qtbot: QtBot, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")

        with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
            worker.start()

        assert_that(blocker.args).is_equal_to([3])

    @pytest.mark.usefixtures("qtbot")
    def test_stop_interrupts(self, search_tree: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [search_tree])
        worker = SearchWorker("hosts")
        worker.start()
        worker.stop()
        assert_that(worker.wait(3000)).is_true()

    def test_max_results_limit(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        for i in range(10):
            (tmp_path / f"hosts_{i}").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 3)

        worker = SearchWorker("hosts")
        count: list[int] = []
        worker.batch_found.connect(lambda batch: count.extend(1 for _ in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(count).is_length(3)

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
        worker.batch_found.connect(lambda batch: count.extend(1 for _ in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(count).is_length(3)

    def test_scandir_permission_error(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr(os, "scandir", MagicMock(side_effect=PermissionError))

        worker = SearchWorker("anything")
        with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
            worker.start()

        assert_that(blocker.args).is_equal_to([0])

    def test_is_dir_os_error(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])

        entry = MagicMock()
        entry.name = "hosts_file"
        entry.path = str(tmp_path / "hosts_file")
        entry.is_dir.side_effect = OSError("Simulated")

        monkeypatch.setattr(os, "scandir", lambda _path: _FakeScandir([entry]))

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(p for p, _s, _d, _id in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(results).is_length(1)

    def test_finds_underscore_with_space_query(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hello_world.txt").touch()
        (tmp_path / "hello-world.py").touch()
        (tmp_path / "helloworld.js").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])

        worker = SearchWorker("hello world")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(results).contains("hello_world.txt")
        assert_that(results).contains("hello-world.py")
        assert_that(results).contains("helloworld.js")

    def test_token_order_independent(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "world_hello.txt").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])

        worker = SearchWorker("hello world")
        results: list[str] = []
        scores: dict[str, int] = {}

        def on_batch(batch: list[tuple[str, int, int, bool]]):
            for path, score, _depth, _is_dir in batch:
                name = Path(path).name
                results.append(name)
                scores[name] = score

        worker.batch_found.connect(on_batch)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(results).contains("world_hello.txt")
        assert_that(scores["world_hello.txt"]).is_equal_to(5)


class TestSkipDirs:
    def test_skips_excluded_dirs(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "hosts_config").touch()
        node_dir = tmp_path / "node_modules"
        node_dir.mkdir()
        (node_dir / "hosts_pkg").touch()
        (tmp_path / "hosts_root").touch()

        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(results).contains("hosts_root")
        assert_that(results).does_not_contain("hosts_config")
        assert_that(results).does_not_contain("hosts_pkg")

    def test_does_not_skip_regular_dirs(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        regular = tmp_path / "subdir"
        regular.mkdir()
        (regular / "hosts_sub").touch()

        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert_that(results).contains("hosts_sub")

    def test_skip_dirs_is_frozenset(self):
        assert_that(SKIP_DIRS).is_instance_of(frozenset)
        assert_that(SKIP_DIRS).contains(".git")
        assert_that(SKIP_DIRS).contains("node_modules")


class TestIterativeWalk:
    def test_deep_directory(self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        current = tmp_path
        for i in range(50):
            current = current / f"level_{i}"
            current.mkdir()
        (current / "hosts_deep").touch()

        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))

        with qtbot.waitSignal(worker.finished, timeout=10000):
            worker.start()

        assert_that(results).contains("hosts_deep")


class TestEarlyReturn:
    @pytest.mark.usefixtures("qtbot")
    def test_run_walk_early_return_at_max_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "test_file").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path, tmp_path])
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 0)

        worker = SearchWorker("test")
        worker.run()

        assert_that(worker._count).is_equal_to(0)

    @pytest.mark.usefixtures("qtbot")
    def test_walk_exits_at_loop_start_when_max_reached(self, monkeypatch: pytest.MonkeyPatch):
        dir_entry = MagicMock()
        dir_entry.name = "subdir"
        dir_entry.path = "C:\\root\\subdir"
        dir_entry.is_dir.return_value = True

        file_entry = MagicMock()
        file_entry.name = "test_file"
        file_entry.path = "C:\\root\\test_file"
        file_entry.is_dir.return_value = False

        monkeypatch.setattr(os, "scandir", lambda _p: _FakeScandir([dir_entry, file_entry]))
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [Path("C:\\root")])
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 1)

        worker = SearchWorker("test")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(p for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).is_length(1)


class TestWalkSearchStrategy:
    @pytest.fixture
    def search_tree(self, tmp_path: Path) -> Path:
        (tmp_path / "hosts").touch()
        (tmp_path / "hosts.txt").write_text("data")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "myhosts").touch()
        (subdir / "readme.txt").write_text("data")
        return tmp_path

    def test_finds_matching(self, search_tree: Path):
        results: list[str] = []
        strategy = WalkSearchStrategy([search_tree])
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(Path(path).name), lambda: False)
        assert_that(sorted(results)).is_equal_to(["hosts", "hosts.txt", "myhosts"])

    def test_respects_max_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        for i in range(10):
            (tmp_path / f"hosts_{i}").touch()
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 3)

        results: list[str] = []
        strategy = WalkSearchStrategy([tmp_path])
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_length(3)

    def test_skips_excluded_dirs(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "hosts_config").touch()
        (tmp_path / "hosts_root").touch()

        results: list[str] = []
        strategy = WalkSearchStrategy([tmp_path])
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(Path(path).name), lambda: False)
        assert_that(results).contains("hosts_root")
        assert_that(results).does_not_contain("hosts_config")

    def test_handles_permission_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(os, "scandir", MagicMock(side_effect=PermissionError))
        strategy = WalkSearchStrategy([tmp_path])
        count = strategy.execute("anything", ["anything"], lambda _p, _s, _d, _id: None, lambda: False)
        assert_that(count).is_equal_to(0)

    def test_interruption(self, search_tree: Path):
        results: list[str] = []
        strategy = WalkSearchStrategy([search_tree])
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: True)
        assert_that(results).is_empty()

    def test_returns_count(self, search_tree: Path):
        count = WalkSearchStrategy([search_tree]).execute(
            "hosts",
            ["hosts"],
            lambda _p, _s, _d, _id: None,
            lambda: False,
        )
        assert_that(count).is_equal_to(3)

    def test_normalized_matching(self, tmp_path: Path):
        (tmp_path / "hello_world.txt").touch()
        (tmp_path / "hello-world.py").touch()
        results: list[str] = []
        strategy = WalkSearchStrategy([tmp_path])
        strategy.execute(
            "hello world",
            ["hello", "world"],
            lambda path, _s, _d, _id: results.append(Path(path).name),
            lambda: False,
        )
        assert_that(results).contains("hello_world.txt")
        assert_that(results).contains("hello-world.py")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
class TestMftSearchStrategy:
    @staticmethod
    def _make_stream_mft(batches):
        def fake_stream_mft(_drive):
            yield from batches

        return fake_stream_mft

    def test_immediate_match(self, monkeypatch: pytest.MonkeyPatch):
        root_dir = MftRecord(file_ref=5, parent_ref=0, name=".", is_dir=True)
        hosts_file = MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False)
        batches = [[root_dir, hosts_file]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_length(1)
        assert_that(results[0]).is_equal_to("C:\\hosts.txt")

    def test_deferred_match(self, monkeypatch: pytest.MonkeyPatch):
        hosts_file = MftRecord(file_ref=10, parent_ref=20, name="hosts.txt", is_dir=False)
        parent_dir = MftRecord(file_ref=20, parent_ref=5, name="Users", is_dir=True)
        batches = [[hosts_file], [parent_dir]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_length(1)
        assert_that(results[0]).is_equal_to("C:\\Users\\hosts.txt")

    def test_orphan_never_emitted(self, monkeypatch: pytest.MonkeyPatch):
        orphan = MftRecord(file_ref=10, parent_ref=999, name="hosts.txt", is_dir=False)
        batches = [[orphan]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_empty()

    def test_skip_dirs_filtering(self, monkeypatch: pytest.MonkeyPatch):
        root_dir = MftRecord(file_ref=5, parent_ref=0, name=".", is_dir=True)
        git_dir = MftRecord(file_ref=20, parent_ref=5, name=".git", is_dir=True)
        hosts_under_git = MftRecord(file_ref=30, parent_ref=20, name="hosts_config", is_dir=False)
        batches = [[root_dir, git_dir, hosts_under_git]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_empty()

    def test_interruption_between_batches(self, monkeypatch: pytest.MonkeyPatch):
        root_dir = MftRecord(file_ref=5, parent_ref=0, name=".", is_dir=True)
        hosts1 = MftRecord(file_ref=10, parent_ref=5, name="hosts1", is_dir=False)
        hosts2 = MftRecord(file_ref=11, parent_ref=5, name="hosts2", is_dir=False)
        batches = [[root_dir, hosts1], [hosts2]]

        call_count = [0]

        def interrupt_after_first():
            call_count[0] += 1
            return call_count[0] > 1

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), interrupt_after_first)
        assert_that(results).is_length(1)

    def test_max_results_stops(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 2)
        root_dir = MftRecord(file_ref=5, parent_ref=0, name=".", is_dir=True)
        records = [MftRecord(file_ref=i, parent_ref=5, name=f"hosts_{i}", is_dir=False) for i in range(10, 20)]
        batches = [[root_dir, *records]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_length(2)

    def test_scores_correct(self, monkeypatch: pytest.MonkeyPatch):
        root_dir = MftRecord(file_ref=5, parent_ref=0, name=".", is_dir=True)
        exact = MftRecord(file_ref=10, parent_ref=5, name="hosts", is_dir=False)
        stem = MftRecord(file_ref=11, parent_ref=5, name="hosts.txt", is_dir=False)
        batches = [[root_dir, exact, stem]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        scores: dict[str, int] = {}
        strategy = MftSearchStrategy("C:")
        strategy.execute(
            "hosts",
            ["hosts"],
            lambda path, score, _d, _id: scores.__setitem__(Path(path).name, score),
            lambda: False,
        )
        assert_that(scores["hosts"]).is_equal_to(0)
        assert_that(scores["hosts.txt"]).is_equal_to(1)

    def test_depth_from_backslashes(self, monkeypatch: pytest.MonkeyPatch):
        root_dir = MftRecord(file_ref=5, parent_ref=0, name=".", is_dir=True)
        subdir = MftRecord(file_ref=10, parent_ref=5, name="Users", is_dir=True)
        deep_file = MftRecord(file_ref=11, parent_ref=10, name="hosts.txt", is_dir=False)
        batches = [[root_dir, subdir, deep_file]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        depths: dict[str, int] = {}
        strategy = MftSearchStrategy("C:")
        strategy.execute(
            "hosts",
            ["hosts"],
            lambda path, _s, depth, _id: depths.__setitem__(Path(path).name, depth),
            lambda: False,
        )
        assert_that(depths["hosts.txt"]).is_equal_to(2)

    def test_retry_pending_skip_dir(self, monkeypatch: pytest.MonkeyPatch):
        hosts_file = MftRecord(file_ref=10, parent_ref=20, name="hosts.txt", is_dir=False)
        git_dir = MftRecord(file_ref=20, parent_ref=5, name=".git", is_dir=True)
        batches = [[hosts_file], [git_dir]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_empty()

    def test_retry_pending_max_results(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "MAX_RESULTS", 1)
        file1 = MftRecord(file_ref=10, parent_ref=20, name="hosts1", is_dir=False)
        file2 = MftRecord(file_ref=11, parent_ref=20, name="hosts2", is_dir=False)
        parent_dir = MftRecord(file_ref=20, parent_ref=5, name="Users", is_dir=True)
        batches = [[file1, file2], [parent_dir]]

        monkeypatch.setattr("seekbar._mft.stream_mft", self._make_stream_mft(batches))
        results: list[str] = []
        strategy = MftSearchStrategy("C:")
        strategy.execute("hosts", ["hosts"], lambda path, _s, _d, _id: results.append(path), lambda: False)
        assert_that(results).is_length(1)

    def test_resolve_pending_emits_resolved(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {10: (5, "hosts.txt", False)}
        strategy._pending = {10: MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False)}
        results: list[str] = []
        strategy._resolve_pending("hosts", lambda path, _s, _d, _id: results.append(path), cleanup=False)
        assert_that(results).is_equal_to(["C:\\hosts.txt"])

    def test_resolve_pending_max_results(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {10: (5, "hosts.txt", False)}
        strategy._pending = {10: MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False)}
        strategy._count = MAX_RESULTS
        results: list[str] = []
        strategy._resolve_pending("hosts", lambda path, _s, _d, _id: results.append(path), cleanup=False)
        assert_that(results).is_empty()

    def test_resolve_pending_cleanup_removes_resolved(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {10: (5, "hosts.txt", False)}
        strategy._pending = {10: MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False)}
        results: list[str] = []
        strategy._resolve_pending("hosts", lambda path, _s, _d, _id: results.append(path), cleanup=True)
        assert_that(results).is_equal_to(["C:\\hosts.txt"])
        assert_that(strategy._pending).is_empty()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
class TestIsUnderSkipDir:
    def test_direct_skip_dir(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {
            10: (20, "file.txt", False),
            20: (5, ".git", True),
        }
        strategy._skip_refs = {20}
        assert_that(strategy._is_under_skip_dir(10)).is_true()

    def test_not_under_skip_dir(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {
            10: (5, "file.txt", False),
        }
        strategy._skip_refs = set()
        assert_that(strategy._is_under_skip_dir(10)).is_false()

    def test_cycle_detection(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {
            10: (11, "a", False),
            11: (10, "b", False),
        }
        strategy._skip_refs = set()
        assert_that(strategy._is_under_skip_dir(10)).is_false()

    def test_root_ref_stops(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {
            10: (5, "file.txt", False),
        }
        strategy._skip_refs = set()
        assert_that(strategy._is_under_skip_dir(10)).is_false()

    def test_uses_skip_cache(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {
            10: (20, "file.txt", False),
            20: (5, "node_modules", True),
        }
        strategy._skip_cache = {20: True}
        assert_that(strategy._is_under_skip_dir(10)).is_true()
        assert_that(strategy._skip_cache[10]).is_true()

    def test_caches_negative_result(self):
        strategy = MftSearchStrategy("C:")
        strategy._records = {
            10: (20, "file.txt", False),
            20: (5, "regular", True),
        }
        strategy._skip_refs = set()
        assert_that(strategy._is_under_skip_dir(10)).is_false()
        assert_that(strategy._skip_cache[10]).is_false()
        assert_that(strategy._skip_cache[20]).is_false()


class TestSearchWorkerStrategy:
    @pytest.mark.usefixtures("qtbot")
    def test_walk_on_unknown_platform(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="freebsd"))

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).contains("hosts")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    @pytest.mark.usefixtures("qtbot")
    def test_mft_on_ntfs_windows(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [Path("C:\\")])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="win32"))

        mock_is_ntfs = MagicMock(return_value=True)
        mock_strategy = MagicMock()
        mock_strategy.return_value.execute.return_value = 5

        monkeypatch.setattr("seekbar._mft.is_ntfs", mock_is_ntfs)
        monkeypatch.setattr("seekbar.search.MftSearchStrategy", mock_strategy)

        worker = SearchWorker("hosts")
        worker.run()

        mock_is_ntfs.assert_called_once_with("C:")
        mock_strategy.assert_called_once_with("C:")
        assert_that(worker._count).is_equal_to(5)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    @pytest.mark.usefixtures("qtbot")
    def test_fallback_on_oserror(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="win32"))

        mock_is_ntfs = MagicMock(return_value=True)
        mock_strategy = MagicMock()
        mock_strategy.return_value.execute.side_effect = OSError("access denied")

        monkeypatch.setattr("seekbar._mft.is_ntfs", mock_is_ntfs)
        monkeypatch.setattr("seekbar.search.MftSearchStrategy", mock_strategy)

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).contains("hosts")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    @pytest.mark.usefixtures("qtbot")
    def test_non_ntfs_uses_walk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="win32"))

        mock_is_ntfs = MagicMock(return_value=False)
        monkeypatch.setattr("seekbar._mft.is_ntfs", mock_is_ntfs)

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).contains("hosts")

    @pytest.mark.usefixtures("qtbot")
    def test_spotlight_on_darwin(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [Path("/")])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="darwin"))
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/mdfind" if cmd == "mdfind" else None)

        mock_strategy = MagicMock()
        mock_strategy.return_value.execute.return_value = 3
        fake_module = types.ModuleType("seekbar._spotlight")
        fake_module.SpotlightSearchStrategy = mock_strategy  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute] - dynamic attr on ModuleType stub
        monkeypatch.setitem(sys.modules, "seekbar._spotlight", fake_module)

        worker = SearchWorker("hosts")
        worker.run()

        mock_strategy.assert_called_once()
        assert_that(worker._count).is_equal_to(3)

    @pytest.mark.usefixtures("qtbot")
    def test_spotlight_fallback_on_oserror(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="darwin"))
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/mdfind" if cmd == "mdfind" else None)

        mock_strategy = MagicMock()
        mock_strategy.return_value.execute.side_effect = OSError("failed")
        fake_module = types.ModuleType("seekbar._spotlight")
        fake_module.SpotlightSearchStrategy = mock_strategy  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute] - dynamic attr on ModuleType stub
        monkeypatch.setitem(sys.modules, "seekbar._spotlight", fake_module)

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).contains("hosts")

    @pytest.mark.usefixtures("qtbot")
    def test_spotlight_not_found_uses_walk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="darwin"))
        monkeypatch.setattr("shutil.which", lambda _cmd: None)

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).contains("hosts")

    @pytest.mark.usefixtures("qtbot")
    def test_locate_on_linux(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [Path("/")])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="linux"))
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/plocate" if cmd == "plocate" else None)

        mock_strategy = MagicMock()
        mock_strategy.return_value.execute.return_value = 4
        fake_module = types.ModuleType("seekbar._locate")
        fake_module.LocateSearchStrategy = mock_strategy  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute] - dynamic attr on ModuleType stub
        monkeypatch.setitem(sys.modules, "seekbar._locate", fake_module)

        worker = SearchWorker("hosts")
        worker.run()

        mock_strategy.assert_called_once_with("/usr/bin/plocate")
        assert_that(worker._count).is_equal_to(4)

    @pytest.mark.usefixtures("qtbot")
    def test_locate_fallback_on_oserror(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="linux"))
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/locate" if cmd == "locate" else None)

        mock_strategy = MagicMock()
        mock_strategy.return_value.execute.side_effect = OSError("failed")
        fake_module = types.ModuleType("seekbar._locate")
        fake_module.LocateSearchStrategy = mock_strategy  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute] - dynamic attr on ModuleType stub
        monkeypatch.setitem(sys.modules, "seekbar._locate", fake_module)

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).contains("hosts")

    @pytest.mark.usefixtures("qtbot")
    def test_locate_not_found_uses_walk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr("seekbar.search.sys", MagicMock(platform="linux"))
        monkeypatch.setattr("shutil.which", lambda _cmd: None)

        worker = SearchWorker("hosts")
        results: list[str] = []
        worker.batch_found.connect(lambda batch: results.extend(Path(p).name for p, _s, _d, _id in batch))
        worker.run()

        assert_that(results).contains("hosts")


class TestBatchBuffer:
    @pytest.mark.usefixtures("qtbot")
    def test_batch_signal_emits_list_of_tuples(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])

        batches: list[list] = []
        worker = SearchWorker("hosts")
        worker.batch_found.connect(lambda batch: batches.append(batch))
        worker.run()

        assert_that(batches).is_length(1)
        assert_that(batches[0]).is_length(1)
        path, score, depth, is_dir = batches[0][0]
        assert_that(Path(path).name).is_equal_to("hosts")
        assert_that(score).is_instance_of(int)
        assert_that(depth).is_instance_of(int)
        assert_that(is_dir).is_instance_of(bool)

    @pytest.mark.usefixtures("qtbot")
    def test_buffer_flushes_at_batch_size(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        for i in range(5):
            (tmp_path / f"hosts_{i}").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr(seekbar.search, "_BATCH_SIZE", 2)

        batches: list[list] = []
        worker = SearchWorker("hosts")
        worker.batch_found.connect(lambda batch: batches.append(batch))
        worker.run()

        assert_that(len(batches)).is_greater_than_or_equal_to(2)
        total_items = sum(len(batch) for batch in batches)
        assert_that(total_items).is_equal_to(5)

    @pytest.mark.usefixtures("qtbot")
    def test_remaining_buffer_flushed_at_end(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "hosts_1").touch()
        (tmp_path / "hosts_2").touch()
        (tmp_path / "hosts_3").touch()
        monkeypatch.setattr(seekbar.search, "discover_roots", lambda: [tmp_path])
        monkeypatch.setattr(seekbar.search, "_BATCH_SIZE", 1000)

        batches: list[list] = []
        worker = SearchWorker("hosts")
        worker.batch_found.connect(lambda batch: batches.append(batch))
        worker.run()

        assert_that(batches).is_length(1)
        assert_that(batches[0]).is_length(3)
