import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

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


_POPEN = "seekbar._subprocess_search.subprocess.Popen"


class TestSubprocessSearch:
    def test_finds_matching_files(self):
        lines = [f"/home/user/hosts.txt{os.linesep}", f"/home/user/readme.md{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert count == 1
        assert "hosts.txt" in results[0][0]

    def test_scores_results(self):
        lines = [f"/home/hosts{os.linesep}", f"/home/hosts.txt{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        scores = [score for _, score, _, _ in results]
        assert scores[0] < scores[1]

    def test_detects_directories(self):
        lines = [f"/home/hosts_dir{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=True):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert results[0][3] is True

    def test_computes_depth(self):
        path = str(Path("/", "home", "user", "docs", "hosts.txt"))
        lines = [f"{path}{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert results[0][2] == 4

    def test_skips_dirs_in_skip_list(self):
        lines = [
            f"/home/user/.git/hosts.txt{os.linesep}",
            f"/home/user/hosts.txt{os.linesep}",
        ]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert len(results) == 1
        assert ".git" not in results[0][0]

    def test_interruption_stops_search(self):
        lines = [f"/home/hosts_{i}.txt{os.linesep}" for i in range(100)]
        process = _FakeProcess(lines)
        call_count = 0

        def interrupt_after_first():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                interrupt_after_first,
            )

        assert count == 1
        assert process._terminated

    def test_max_results_stops_search(self):
        lines = [f"/home/hosts_{i}.txt{os.linesep}" for i in range(MAX_RESULTS + 10)]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert count == MAX_RESULTS

    def test_empty_output(self):
        process = _FakeProcess([])
        results: list[tuple] = []

        with patch(_POPEN, return_value=process):
            count = subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert count == 0
        assert results == []

    def test_skips_empty_lines(self):
        lines = [os.linesep, f"/home/hosts.txt{os.linesep}", os.linesep]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "hosts",
                ["hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert count == 1

    def test_non_matching_files_filtered(self):
        lines = [f"/home/readme.md{os.linesep}", f"/home/changelog.txt{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process):
            count = subprocess_search(["cmd"], "hosts", ["hosts"], lambda *args: results.append(args), lambda: False)

        assert count == 0
        assert results == []

    def test_process_terminated_on_success(self):
        lines = [f"/home/hosts.txt{os.linesep}"]
        process = _FakeProcess(lines)

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *_args: None, lambda: False)

        assert process._terminated

    def test_process_terminated_on_exception(self):
        process = MagicMock()
        process.stdout = iter([f"/home/hosts.txt{os.linesep}"])

        def raise_error(*_args):
            msg = "test error"
            raise RuntimeError(msg)

        with (
            patch(_POPEN, return_value=process),
            patch.object(Path, "is_dir", side_effect=raise_error),
            pytest.raises(RuntimeError),
        ):
            subprocess_search(["cmd"], "hosts", ["hosts"], lambda *_args: None, lambda: False)

        process.terminate.assert_called_once()
        process.wait.assert_called_once()

    def test_normalized_matching(self):
        lines = [f"/home/my_hosts_file.txt{os.linesep}"]
        process = _FakeProcess(lines)
        results: list[tuple] = []

        with patch(_POPEN, return_value=process), patch.object(Path, "is_dir", return_value=False):
            count = subprocess_search(
                ["cmd"],
                "my hosts",
                ["my", "hosts"],
                lambda *args: results.append(args),
                lambda: False,
            )

        assert count == 1
