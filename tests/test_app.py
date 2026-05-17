from __future__ import annotations

import platform
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtWidgets import QStyleOptionViewItem

import filefinder.app

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from filefinder.app import MainWindow


class TestMainWindow:
    def test_window_title(self, window: MainWindow):
        assert window.windowTitle() == "FileFinder"

    def test_frameless(self, window: MainWindow):
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint

    def test_fixed_width(self, window: MainWindow):
        assert window.width() == 620

    def test_initial_results_hidden(self, window: MainWindow):
        assert window._result_list.isHidden()
        assert window._separator.isHidden()

    def test_initial_status_empty(self, window: MainWindow):
        assert window._status_label.text() == ""

    def test_initial_height(self, window: MainWindow):
        expected = window._SEARCH_HEIGHT + window._MARGIN * 2
        assert window.height() == expected

    def test_delegate_size_hint(self, window: MainWindow):
        delegate = window._result_list.itemDelegate()
        size = delegate.sizeHint(QStyleOptionViewItem(), QModelIndex())
        assert size.height() == 52


class TestSortedInsertion:
    def test_sorted_by_score(self, window: MainWindow):
        window._add_result("C:/dir/xhostsy", 4)
        window._add_result("C:/dir/hosts", 0)
        window._add_result("C:/dir/hosts.txt", 1)

        paths = [window._result_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window._result_list.count())]
        assert paths == ["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/xhostsy"]

    def test_secondary_sort_by_name_length(self, window: MainWindow):
        window._add_result("C:/dir/ab_hosts", 4)
        window._add_result("C:/dir/a_hosts", 4)

        names = [
            Path(window._result_list.item(i).data(Qt.ItemDataRole.UserRole)).name
            for i in range(window._result_list.count())
        ]
        assert names == ["a_hosts", "ab_hosts"]

    def test_results_become_visible(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        assert not window._result_list.isHidden()
        assert not window._separator.isHidden()


class TestHeightSync:
    def test_grows_with_single_result(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        expected = window._SEARCH_HEIGHT + 1 + window._ITEM_HEIGHT + window._RADIUS + window._MARGIN * 2
        assert window.height() == expected

    def test_capped_at_max_visible(self, window: MainWindow):
        for i in range(window._MAX_VISIBLE + 5):
            window._add_result(f"C:/test/file_{i}.txt", 4)

        expected = (
            window._SEARCH_HEIGHT + 1 + window._MAX_VISIBLE * window._ITEM_HEIGHT + window._RADIUS + window._MARGIN * 2
        )
        assert window.height() == expected


class TestSearchLifecycle:
    def test_clear_text_resets(self, window: MainWindow):
        window._search_input.setText("query")
        window._add_result("C:/test/file.txt", 4)
        window._search_input.setText("")
        assert window._result_list.count() == 0
        assert window._status_label.text() == ""
        assert window._result_list.isHidden()

    def test_status_updates_on_add(self, window: MainWindow):
        window._add_result("C:/test/a.txt", 4)
        assert "1" in window._status_label.text()
        window._add_result("C:/test/b.txt", 4)
        assert "2" in window._status_label.text()

    def test_done_no_results(self, window: MainWindow):
        window._on_search_done(0)
        assert window._status_label.text() == "no results"

    def test_done_with_results(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        window._on_search_done(1)
        assert "1" in window._status_label.text()

    def test_start_search(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.setText("test")
        mock_worker = MagicMock()
        monkeypatch.setattr(filefinder.app, "SearchWorker", lambda _q: mock_worker)
        window._start_search()
        assert window._status_label.text() == "searching..."
        mock_worker.start.assert_called_once()

    def test_start_search_empty(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.setText("  ")
        mock_cls = MagicMock()
        monkeypatch.setattr(filefinder.app, "SearchWorker", mock_cls)
        window._start_search()
        mock_cls.assert_not_called()

    def test_start_search_immediate(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.setText("test")
        mock_worker = MagicMock()
        monkeypatch.setattr(filefinder.app, "SearchWorker", lambda _q: mock_worker)
        window._start_search_immediate()
        mock_worker.start.assert_called_once()

    def test_stop_running_search(self, window: MainWindow):
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        window._worker = mock_worker
        window._stop_search()
        mock_worker.stop.assert_called_once()
        mock_worker.wait.assert_called_once_with(3000)
        assert window._worker is None


class TestWindowDragging:
    def test_press_sets_drag_pos(self, window: MainWindow):
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.LeftButton
        event.globalPosition.return_value.toPoint.return_value = QPoint(500, 300)
        window.mousePressEvent(event)
        assert window._drag_pos is not None

    def test_press_right_button_no_drag(self, window: MainWindow):
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.RightButton
        window.mousePressEvent(event)
        assert window._drag_pos is None

    def test_move_with_drag(self, window: MainWindow):
        window._drag_pos = QPoint(10, 10)
        event = MagicMock()
        event.buttons.return_value = Qt.MouseButton.LeftButton
        event.globalPosition.return_value.toPoint.return_value = QPoint(200, 200)
        window.mouseMoveEvent(event)
        assert window.pos() == QPoint(190, 190)

    def test_move_without_drag(self, window: MainWindow):
        initial_pos = window.pos()
        event = MagicMock()
        event.buttons.return_value = Qt.MouseButton.LeftButton
        event.globalPosition.return_value.toPoint.return_value = QPoint(200, 200)
        window.mouseMoveEvent(event)
        assert window.pos() == initial_pos

    def test_release_clears_drag(self, window: MainWindow):
        window._drag_pos = QPoint(10, 10)
        event = MagicMock()
        window.mouseReleaseEvent(event)
        assert window._drag_pos is None


class TestInteraction:
    def test_escape_closes(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.keyClick(window, Qt.Key.Key_Escape)
        assert not window.isVisible()

    def test_close_button(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.mouseClick(window._close_button, Qt.MouseButton.LeftButton)
        assert not window.isVisible()

    def test_non_escape_key(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.keyClick(window, Qt.Key.Key_A)
        assert window.isVisible()


class TestContextMenu:
    def test_with_item(self, window: MainWindow):
        window._add_result("C:/test/hosts", 0)
        window.show()
        window._show_context_menu(QPoint(10, 10))

    def test_no_item(self, window: MainWindow):
        window._show_context_menu(QPoint(9999, 9999))


class TestFileOpening:
    def test_open_file(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._add_result("C:/test/hosts", 0)
        item = window._result_list.item(0)
        mock_desktop = MagicMock()
        monkeypatch.setattr(filefinder.app, "QDesktopServices", mock_desktop)
        window._open_file(item)
        mock_desktop.openUrl.assert_called_once()

    def test_open_file_by_path(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        mock_desktop = MagicMock()
        monkeypatch.setattr(filefinder.app, "QDesktopServices", mock_desktop)
        window._open_file_by_path("C:/test/hosts")
        mock_desktop.openUrl.assert_called_once()

    def test_open_folder_windows(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        mock_popen = MagicMock()
        monkeypatch.setattr(filefinder.app.subprocess, "Popen", mock_popen)
        window._open_folder("C:/test/hosts")
        mock_popen.assert_called_once_with(["explorer", "/select,", "C:/test/hosts"])

    def test_open_folder_darwin(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        mock_popen = MagicMock()
        monkeypatch.setattr(filefinder.app.subprocess, "Popen", mock_popen)
        window._open_folder("/Users/test/hosts")
        mock_popen.assert_called_once_with(["open", "-R", "/Users/test/hosts"])

    def test_open_folder_fallback(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        mock_desktop = MagicMock()
        monkeypatch.setattr(filefinder.app, "QDesktopServices", mock_desktop)
        window._open_folder("/home/test/hosts")
        mock_desktop.openUrl.assert_called_once()
