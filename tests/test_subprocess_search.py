import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from assertpy2 import assert_that

if TYPE_CHECKING:
    from collections.abc import Sequence

# noinspection PyProtectedMember
from seekbar._subprocess_search import subprocess_search
from seekbar.search import MAX_RESULTS


class _FakeProcess:
    def __init__(self, lines: Sequence[str]):
        self.stdout = iter(lines)
        self._terminated = False

    def terminate(self):
        self._terminated = True

    def wait(self):
        pass


class _HangingProcess:
    """Backend that produces no output and blocks until terminated (simulates a hung mdfind/locate)."""

    def __init__(self):
        self._released = threading.Event()
        self._terminated = False
        self.stdout = self

    def __iter__(self):
        return self

    def __next__(self):
        self._released.wait()
        raise StopIteration

    def terminate(self):
        self._terminated = True
        self._released.set()

    def wait(self):
        pass


_POPEN = "seekbar._subprocess_search.subprocess.Popen"


class TestSubprocessSearch:
    def test_finds_matching_files(self):
        lines = [f"/home/user/hosts.txt{os.linesep}", f"/home/user/readme.md{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert_that(count).is_equal_to(1)
        assert_that(results[0][0]).contains("hosts.txt")

    def test_scores_results(self):
        lines = [f"/home/hosts{os.linesep}", f"/home/hosts.txt{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        scores = [score for _, score, _, _ in results]
        assert_that(scores[0]).is_less_than(scores[1])

    def test_detects_directories(self):
        lines = [f"/home/hosts_dir{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=True):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert_that(results[0][3]).is_true()

    def test_computes_depth(self):
        path = str(Path("/", "home", "user", "docs", "hosts.txt"))
        lines = [f"{path}{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert_that(results[0][2]).is_equal_to(4)

    def test_skips_dirs_in_skip_list(self):
        lines = [
            f"/home/user/.git/hosts.txt{os.linesep}",
            f"/home/user/hosts.txt{os.linesep}",
        ]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert_that(results).is_length(1)
        assert_that(results[0][0]).does_not_contain(".git")

    def test_interruption_stops_search(self):
        lines = [f"/home/hosts_{i}.txt{os.linesep}" for i in range(100)]
        process = _FakeProcess(lines)
        call_count = 0

        def interrupt_after_first():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                interrupt_after_first,
            )

        assert_that(count).is_equal_to(1)
        assert_that(process._terminated).is_true()

    def test_max_results_stops_search(self):
        lines = [f"/home/hosts_{i}.txt{os.linesep}" for i in range(MAX_RESULTS + 10)]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert_that(count).is_equal_to(MAX_RESULTS)

    def test_empty_output(self):
        process = _FakeProcess([])
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process):
            count = subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert_that(count).is_equal_to(0)
        assert_that(results).is_empty()

    def test_skips_empty_lines(self):
        lines = [os.linesep, f"/home/hosts.txt{os.linesep}", os.linesep]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert_that(count).is_equal_to(1)

    def test_non_matching_files_filtered(self):
        lines = [f"/home/readme.md{os.linesep}", f"/home/changelog.txt{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process):
            count = subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert_that(count).is_equal_to(0)
        assert_that(results).is_empty()

    def test_process_terminated_on_success(self):
        lines = [f"/home/hosts.txt{os.linesep}"]
        process = _FakeProcess(lines)

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *_args: None, lambda: False)

        assert_that(process._terminated).is_true()

    def test_process_terminated_on_exception(self):
        process = MagicMock()
        process.stdout = iter([f"/home/hosts.txt{os.linesep}"])

        def raise_error(*_args):
            msg = "test error"
            raise RuntimeError(msg)

        with (
            patch(_POPEN, return_value=process),
            patch.object(Path, "is_dir", side_effect=raise_error),
        ):
            assert_that(subprocess_search).raises(RuntimeError).when_called_with(
                ["cmd"], "hosts", ["hosts"], lambda *_args: None, lambda: False
            )

        process.terminate.assert_called_once()
        process.wait.assert_called_once()

    def test_normalized_matching(self):
        lines = [f"/home/my_hosts_file.txt{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "my hosts",
                ["my", "hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert_that(count).is_equal_to(1)

    def test_interruption_while_waiting_for_output(self):
        process = _HangingProcess()
        call_count = 0

        def interrupt_after_first():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process):
            count = subprocess_search(
                ["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), interrupt_after_first
            )

        assert_that(count).is_equal_to(0)
        assert_that(process._terminated).is_true()

    def test_idle_timeout_terminates_hung_backend(self, monkeypatch):
        monkeypatch.setattr("seekbar._subprocess_search._POLL_INTERVAL", 0.01)
        monkeypatch.setattr("seekbar._subprocess_search._IDLE_TIMEOUT", 0.05)
        process = _HangingProcess()
        results: list[tuple[str, int, int, bool]] = []

        with patch(_POPEN, return_value=process):
            count = subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert_that(count).is_equal_to(0)
        assert_that(process._terminated).is_true()
