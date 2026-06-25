import ctypes
import ctypes.wintypes
import json
import platform
import sys
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from assertpy2 import assert_that
from hypothesis import given, settings as hypothesis_settings
from hypothesis import strategies as st
from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPointF, QSettings, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPixmap
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QStyleOptionViewItem, QSystemTrayIcon

import seekbar.app

# noinspection PyProtectedMember
from seekbar.app import (
    MainWindow,
    _basename_length,
    _FONT_FAMILY,
    _handle_version_flag,
    _SingleInstanceGuard,
    _IS_DIR_ROLE,
    _NAME_ROLE,
    _PARENT_ROLE,
    _RecencyStore,
    _ResultModel,
    SETTINGS_APP,
    SETTINGS_ORG,
    _system_font_family,
)
from seekbar.search import MAX_RESULTS
from seekbar.theme import ACCENTS, DARK_THEME, DEFAULT_ACCENT, LIGHT_THEME, ThemeMode, TrayIconMode

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestMainWindow:
    def test_window_title(self, window: MainWindow):
        assert_that(window.windowTitle()).is_equal_to("Seekbar")

    def test_frameless(self, window: MainWindow):
        assert_that(window.windowFlags() & Qt.WindowType.FramelessWindowHint).is_true()

    def test_fixed_width(self, window: MainWindow):
        assert_that(window.width()).is_equal_to(620)

    def test_initial_results_hidden(self, window: MainWindow):
        assert_that(window._result_list.isHidden()).is_true()
        assert_that(window._separator.isHidden()).is_true()

    def test_initial_status_empty(self, window: MainWindow):
        assert_that(window._status_label.text()).is_empty()

    def test_initial_height(self, window: MainWindow):
        expected = window._search_height + window._MARGIN * 2
        assert_that(window.height()).is_equal_to(expected)

    def test_accessible_names(self, window: MainWindow):
        assert_that(window._search_input.accessibleName()).is_equal_to("Search input")
        assert_that(window._result_list.accessibleName()).is_equal_to("Search results")
        assert_that(window._close_button.accessibleName()).is_equal_to("Close")

    def test_delegate_size_hint(self, window: MainWindow):
        delegate = window._delegate
        size = delegate.sizeHint(QStyleOptionViewItem(), QModelIndex())
        assert_that(size.height()).is_equal_to(delegate.item_height)

    def test_delegate_item_height_from_metrics(self, window: MainWindow):
        delegate = window._delegate
        expected = delegate._name_metrics.height() + delegate._path_metrics.height() + delegate._VERTICAL_PADDING
        assert_that(delegate.item_height).is_equal_to(expected)

    def test_delegate_has_cached_fonts(self, window: MainWindow):
        delegate = window._result_list.itemDelegate()
        assert_that(hasattr(delegate, "_name_font")).is_true()
        assert_that(hasattr(delegate, "_path_font")).is_true()
        assert_that(hasattr(delegate, "_name_metrics")).is_true()
        assert_that(hasattr(delegate, "_path_metrics")).is_true()


class TestFontFamily:
    def test_font_family_not_empty(self):
        assert_that(_FONT_FAMILY).is_not_empty()
        assert_that(_FONT_FAMILY).is_instance_of(str)

    def test_windows_font(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        assert_that(_system_font_family()).is_equal_to("Segoe UI")

    def test_darwin_font(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        assert_that(_system_font_family()).is_equal_to(".AppleSystemUIFont")

    def test_linux_font(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        assert_that(_system_font_family()).is_equal_to("Sans")


class TestSortedInsertion:
    def test_sorted_by_score(self, window: MainWindow):
        window._add_result("C:/dir/xhostsy", 4)
        window._add_result("C:/dir/hosts", 0)
        window._add_result("C:/dir/hosts.txt", 1)

        paths = [window._result_model.path_at(i) for i in range(window._result_model.rowCount())]
        assert_that(paths).is_equal_to(["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/xhostsy"])

    def test_secondary_sort_by_name_length(self, window: MainWindow):
        window._add_result("C:/dir/ab_hosts", 4)
        window._add_result("C:/dir/a_hosts", 4)

        names = [Path(window._result_model.path_at(i)).name for i in range(window._result_model.rowCount())]
        assert_that(names).is_equal_to(["a_hosts", "ab_hosts"])

    def test_depth_sort_tiebreaker(self, window: MainWindow):
        window._add_result("C:/a/b/c/hosts", 0, depth=3)
        window._add_result("C:/hosts", 0, depth=1)

        paths = [window._result_model.path_at(i) for i in range(window._result_model.rowCount())]
        assert_that(paths).is_equal_to(["C:/hosts", "C:/a/b/c/hosts"])

    def test_results_become_visible(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        assert_that(window._result_list.isHidden()).is_false()
        assert_that(window._separator.isHidden()).is_false()


class TestHeightSync:
    def test_grows_with_single_result(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        item_h = window._delegate.item_height
        expected = window._search_height + 1 + item_h + window._RADIUS + window._MARGIN * 2
        assert_that(window.height()).is_equal_to(expected)

    def test_capped_at_max_visible(self, window: MainWindow):
        for i in range(window._MAX_VISIBLE + 5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        item_h = window._delegate.item_height
        expected = window._search_height + 1 + window._MAX_VISIBLE * item_h + window._RADIUS + window._MARGIN * 2
        assert_that(window.height()).is_equal_to(expected)

    def test_fit_card_never_below_content(self, window: MainWindow):
        window._content_height = 300
        # A short (mid-grow) window must not squeeze the card below its content height.
        window._fit_card(100)
        assert_that(window._card.height()).is_equal_to(300)
        # A taller (mid-shrink) window must be fully covered by the card, not the desktop.
        window._fit_card(500)
        assert_that(window._card.height()).is_equal_to(500 - window._MARGIN * 2)


class TestSearchLifecycle:
    def test_clear_text_resets(self, window: MainWindow):
        window._search_input.setText("query")
        window._add_result("C:/test/file.txt", 4)
        window._search_input.setText("")
        assert_that(window._result_model.rowCount()).is_equal_to(0)
        assert_that(window._status_label.text()).is_empty()
        assert_that(window._result_list.isHidden()).is_true()

    def test_status_updates_on_add(self, window: MainWindow):
        window._add_result("C:/test/a.txt", 4)
        assert_that(window._status_label.text()).contains("1")
        window._add_result("C:/test/b.txt", 4)
        assert_that(window._status_label.text()).contains("2")

    def test_done_no_results(self, window: MainWindow):
        window._on_search_done(0)
        assert_that(window._status_label.text()).is_equal_to("no results")

    def test_done_with_results(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        window._on_search_done(1)
        assert_that(window._status_label.text()).contains("1")

    def test_add_result_ignored_without_worker(self, window: MainWindow):
        window._worker = None
        window._add_result("C:/test/stale.txt", 4)
        assert_that(window._result_model.rowCount()).is_equal_to(0)

    def test_done_ignored_without_worker(self, window: MainWindow):
        window._worker = None
        window._status_label.setText("searching.")
        window._on_search_done(0)
        assert_that(window._status_label.text()).is_equal_to("searching.")

    def test_clear_text_stops_debounce_timer(self, window: MainWindow):
        window._search_input.setText("query")
        assert_that(window._debounce_timer.isActive()).is_true()
        window._search_input.setText("")
        assert_that(window._debounce_timer.isActive()).is_false()

    def test_typing_shows_searching_immediately(self, window: MainWindow):
        window._on_search_done(0)
        assert_that(window._status_label.text()).is_equal_to("no results")
        window._search_input.setText("newquery")
        assert_that(window._status_label.text()).is_equal_to("searching.")

    def test_typing_stops_previous_search(self, window: MainWindow):
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        window._worker = mock_worker
        window._search_input.setText("newquery")
        mock_worker.stop.assert_called_once()

    def test_start_search(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.setText("test")
        mock_worker = MagicMock()
        monkeypatch.setattr(seekbar.app, "SearchWorker", lambda _q: mock_worker)
        window._start_search()
        assert_that(window._status_label.text()).is_equal_to("searching.")
        mock_worker.start.assert_called_once()

    def test_start_search_empty(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.setText("  ")
        mock_cls = MagicMock()
        monkeypatch.setattr(seekbar.app, "SearchWorker", mock_cls)
        window._start_search()
        mock_cls.assert_not_called()

    def test_start_search_starts_animation_if_inactive(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.blockSignals(True)
        window._search_input.setText("test")
        window._search_input.blockSignals(False)
        assert_that(window._searching_timer.isActive()).is_false()
        mock_worker = MagicMock()
        monkeypatch.setattr(seekbar.app, "SearchWorker", lambda _q: mock_worker)
        window._start_search()
        assert_that(window._searching_timer.isActive()).is_true()

    def test_start_search_immediate(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.setText("test")
        mock_worker = MagicMock()
        monkeypatch.setattr(seekbar.app, "SearchWorker", lambda _q: mock_worker)
        window._start_search_immediate()
        mock_worker.start.assert_called_once()

    def test_stop_running_search(self, window: MainWindow):
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        window._worker = mock_worker
        window._stop_search()
        mock_worker.stop.assert_called_once()
        mock_worker.wait.assert_called_once_with(3000)
        assert_that(window._worker).is_none()


class TestWindowDragging:
    def test_press_sets_drag_pos(self, window: MainWindow):
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.LeftButton
        event.globalPosition.return_value.toPoint.return_value = QPoint(500, 300)
        window.mousePressEvent(event)
        assert_that(window._drag_pos).is_not_none()

    def test_press_right_button_no_drag(self, window: MainWindow):
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.RightButton
        window.mousePressEvent(event)
        assert_that(window._drag_pos).is_none()

    def test_move_with_drag(self, window: MainWindow):
        window._drag_pos = QPoint(10, 10)
        event = MagicMock()
        event.buttons.return_value = Qt.MouseButton.LeftButton
        event.globalPosition.return_value.toPoint.return_value = QPoint(200, 200)
        window.mouseMoveEvent(event)
        assert_that(window.pos()).is_equal_to(QPoint(190, 190))

    def test_move_without_drag(self, window: MainWindow):
        initial_pos = window.pos()
        event = MagicMock()
        event.buttons.return_value = Qt.MouseButton.LeftButton
        event.globalPosition.return_value.toPoint.return_value = QPoint(200, 200)
        window.mouseMoveEvent(event)
        assert_that(window.pos()).is_equal_to(initial_pos)

    def test_release_clears_drag(self, window: MainWindow):
        window._drag_pos = QPoint(10, 10)
        event = MagicMock()
        window.mouseReleaseEvent(event)
        assert_that(window._drag_pos).is_none()


class TestKeyboardNavigation:
    def test_escape_clears_text_first(self, window: MainWindow, qtbot: QtBot):
        window.show()
        window._search_input.setText("query")
        qtbot.keyClick(window, Qt.Key.Key_Escape)
        assert_that(window._search_input.text()).is_empty()
        assert_that(window.isVisible()).is_true()

    def test_escape_closes_when_empty(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.keyClick(window, Qt.Key.Key_Escape)
        assert_that(window.isVisible()).is_false()

    def test_close_button(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.mouseClick(window._close_button, Qt.MouseButton.LeftButton)
        assert_that(window.isVisible()).is_false()

    def test_tab_does_not_change_focus(self, window: MainWindow):
        assert_that(window.focusNextPrevChild(True)).is_true()

    def test_backtab_does_not_change_focus(self, window: MainWindow):
        assert_that(window.focusNextPrevChild(False)).is_true()

    def test_non_escape_key(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.keyClick(window, Qt.Key.Key_A)
        assert_that(window.isVisible()).is_true()

    def test_key_down_selects_first(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert_that(window._current_row()).is_equal_to(0)

    def test_key_down_advances(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._select_row(0)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert_that(window._current_row()).is_equal_to(1)

    def test_key_down_stays_at_bottom(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._select_row(1)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert_that(window._current_row()).is_equal_to(1)

    def test_key_up_stays_at_top(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._select_row(0)
        qtbot.keyClick(window, Qt.Key.Key_Up)
        assert_that(window._current_row()).is_equal_to(0)

    def test_move_selection_empty_list(self, window: MainWindow):
        window._move_selection(1)
        assert_that(window._current_row()).is_equal_to(-1)

    def test_enter_opens_selected(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._add_result("C:/test/hosts", 0)
        window._select_row(0)
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._activate_selected()
        mock_desktop.openUrl.assert_called_once()

    def test_return_key_via_key_press_event(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._add_result("C:/test/hosts", 0)
        window._select_row(0)
        window._result_list.setFocus()
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        qtbot_key_event = MagicMock()
        qtbot_key_event.key.return_value = Qt.Key.Key_Return
        window.keyPressEvent(qtbot_key_event)
        mock_desktop.openUrl.assert_called_once()

    def test_enter_without_selection_searches(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._search_input.setText("test")
        mock_worker = MagicMock()
        monkeypatch.setattr(seekbar.app, "SearchWorker", lambda _q: mock_worker)
        window._activate_selected()
        mock_worker.start.assert_called_once()

    def test_ctrl_t_cycles_theme(self, window: MainWindow, qtbot: QtBot):
        initial_mode = window._theme_mode
        qtbot.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
        assert_that(window._theme_mode).is_not_equal_to(initial_mode)

    def test_ctrl_q_quits(self, window: MainWindow, qtbot: QtBot):
        with patch.object(seekbar.app.QApplication, "quit") as mock_quit:
            qtbot.keyClick(window, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier)
            mock_quit.assert_called_once()


class TestContextMenu:
    def test_with_item(self, window: MainWindow):
        window._add_result("C:/test/hosts", 0)
        window.show()
        window._show_context_menu(QPoint(10, 10))

    def test_no_item(self, window: MainWindow):
        window._show_context_menu(QPoint(9999, 9999))

    def test_file_item_labels_open_file(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        captured: list = []
        monkeypatch.setattr(seekbar.app.QMenu, "popup", lambda menu, *_args: captured.append(menu))
        window._add_result("C:/test/file.txt", 0)
        window.show()
        window._show_context_menu(QPoint(10, 10))
        assert_that(captured[0].actions()[0].text()).is_equal_to("Open file")

    def test_dir_item_labels_open_folder(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        captured: list = []
        monkeypatch.setattr(seekbar.app.QMenu, "popup", lambda menu, *_args: captured.append(menu))
        window._add_result("C:/test/folder", 0, is_dir=True)
        window.show()
        window._show_context_menu(QPoint(10, 10))
        assert_that(captured[0].actions()[0].text()).is_equal_to("Open folder")


class TestFileOpening:
    def test_open_file(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._add_result("C:/test/hosts", 0)
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_index(window._result_model.index(0))
        mock_desktop.openUrl.assert_called_once()

    def test_open_file_by_path(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_file_by_path("C:/test/hosts")
        mock_desktop.openUrl.assert_called_once()

    def test_open_records_recency(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.app, "QDesktopServices", MagicMock())
        window._open_file_by_path("C:/test/hosts")
        assert_that(window._recency.rank("C:/test/hosts")).is_equal_to(0)

    def test_open_folder_windows(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        mock_run = MagicMock()
        monkeypatch.setattr(seekbar.app.subprocess, "run", mock_run)
        window._open_folder("C:/test/hosts")
        mock_run.assert_called_once_with(["explorer", "/select,", "C:/test/hosts"], check=False)

    def test_open_folder_darwin(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        mock_run = MagicMock()
        monkeypatch.setattr(seekbar.app.subprocess, "run", mock_run)
        window._open_folder("/Users/test/hosts")
        mock_run.assert_called_once_with(["open", "-R", "/Users/test/hosts"], check=False)

    def test_open_folder_fallback(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_folder("/home/test/hosts")
        mock_desktop.openUrl.assert_called_once()


class TestIsDirRole:
    def test_file_default(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        assert_that(window._result_model.data(window._result_model.index(0), _IS_DIR_ROLE)).is_false()

    def test_directory_stored(self, window: MainWindow):
        window._add_result("C:/test/folder", 4, is_dir=True)
        assert_that(window._result_model.data(window._result_model.index(0), _IS_DIR_ROLE)).is_true()


class TestResultDelegate:
    def test_has_folder_icon(self, window: MainWindow):
        delegate = window._delegate
        assert_that(delegate.folder_icon).is_not_none()
        assert_that(delegate.folder_icon.isNull()).is_false()

    def test_has_file_icon(self, window: MainWindow):
        delegate = window._delegate
        assert_that(delegate.file_icon).is_not_none()
        assert_that(delegate.file_icon.isNull()).is_false()

    def test_icon_size(self, window: MainWindow):
        delegate = window._delegate
        assert_that(delegate.folder_icon.width()).is_equal_to(20)
        assert_that(delegate.folder_icon.height()).is_equal_to(20)
        assert_that(delegate.file_icon.width()).is_equal_to(20)
        assert_that(delegate.file_icon.height()).is_equal_to(20)

    def test_set_theme_rebuilds_icons(self, window: MainWindow):
        delegate = window._delegate
        old_folder = delegate.folder_icon
        old_file = delegate.file_icon
        delegate.set_theme(LIGHT_THEME)
        assert_that(delegate._theme).is_same_as(LIGHT_THEME)
        assert_that(delegate.folder_icon).is_not_same_as(old_folder)
        assert_that(delegate.file_icon).is_not_same_as(old_file)
        assert_that(delegate.folder_icon.isNull()).is_false()
        assert_that(delegate.file_icon.isNull()).is_false()


class TestThemeSwitching:
    def test_default_mode_is_auto(self, window: MainWindow):
        assert_that(window._theme_mode).is_equal_to(ThemeMode.AUTO)

    def test_cycle_auto_to_light(self, window: MainWindow):
        window._cycle_theme()
        assert_that(window._theme_mode).is_equal_to(ThemeMode.LIGHT)

    def test_cycle_light_to_dark(self, window: MainWindow):
        window._theme_mode = ThemeMode.LIGHT
        window._cycle_theme()
        assert_that(window._theme_mode).is_equal_to(ThemeMode.DARK)

    def test_cycle_dark_to_auto(self, window: MainWindow):
        window._theme_mode = ThemeMode.DARK
        window._cycle_theme()
        assert_that(window._theme_mode).is_equal_to(ThemeMode.AUTO)

    def test_cycle_applies_theme(self, window: MainWindow):
        window._cycle_theme()
        assert_that(window._theme).is_equal_to(LIGHT_THEME)

    def test_set_theme_updates_delegate(self, window: MainWindow):
        window._set_theme(LIGHT_THEME)
        assert_that(window._delegate._theme).is_same_as(LIGHT_THEME)

    def test_system_theme_change_in_auto_mode(self, window: MainWindow):
        window._theme_mode = ThemeMode.AUTO
        mock_app = MagicMock()
        mock_app.styleHints.return_value.colorScheme.return_value = Qt.ColorScheme.Light
        with patch("seekbar.theme.QGuiApplication.instance", return_value=mock_app):
            window._on_system_theme_changed(Qt.ColorScheme.Light)
        assert_that(window._theme).is_equal_to(LIGHT_THEME)

    def test_system_theme_change_ignored_in_manual_mode(self, window: MainWindow):
        window._theme_mode = ThemeMode.DARK
        window._set_theme(DARK_THEME)
        window._on_system_theme_changed(Qt.ColorScheme.Light)
        assert_that(window._theme).is_same_as(DARK_THEME)

    def test_close_icon_updates_on_theme_switch(self, window: MainWindow):
        old_icon = window._close_button.icon()
        window._set_theme(LIGHT_THEME)
        new_icon = window._close_button.icon()
        assert_that(old_icon.cacheKey()).is_not_equal_to(new_icon.cacheKey())


class TestThemePersistence:
    def test_cycle_saves_to_settings(self, window: MainWindow):
        window._cycle_theme()
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        assert_that(settings.value("theme_mode")).is_equal_to(ThemeMode.LIGHT.value)

    def test_load_saved_mode(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("theme_mode", "dark")
        loaded = window._load_theme_mode()
        assert_that(loaded).is_equal_to(ThemeMode.DARK)

    def test_load_invalid_mode_defaults_to_auto(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("theme_mode", "garbage")
        loaded = window._load_theme_mode()
        assert_that(loaded).is_equal_to(ThemeMode.AUTO)

    def test_load_missing_key_defaults_to_auto(self, window: MainWindow):
        loaded = window._load_theme_mode()
        assert_that(loaded).is_equal_to(ThemeMode.AUTO)


class TestResultLimitIndicator:
    def test_format_count_below_limit(self, window: MainWindow):
        assert_that(window._format_count(50)).is_equal_to("50 results")

    def test_format_count_at_limit(self, window: MainWindow):
        assert_that(window._format_count(MAX_RESULTS)).is_equal_to(f"{MAX_RESULTS}+ results")

    def test_format_count_above_limit(self, window: MainWindow):
        assert_that(window._format_count(MAX_RESULTS + 1)).is_equal_to(f"{MAX_RESULTS}+ results")

    def test_status_shows_limit_on_done(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.app, "MAX_RESULTS", 3)
        for i in range(3):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._on_search_done(3)
        assert_that(window._status_label.text()).contains("3+")


class TestWindowPositionPersistence:
    def test_saves_position_on_close(self, window: MainWindow):
        window.show()
        window.move(QPoint(100, 200))
        window.close()
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        assert_that(settings.value("window_x")).is_equal_to(100)
        assert_that(settings.value("window_y")).is_equal_to(200)

    def test_restores_saved_position(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        screen = window.screen().geometry()
        pos_x = screen.x() + 50
        pos_y = screen.y() + 50
        settings.setValue("window_x", pos_x)
        settings.setValue("window_y", pos_y)
        loaded = window._load_window_position()
        assert_that(loaded).is_equal_to(QPoint(pos_x, pos_y))

    def test_window_uses_saved_position_on_init(self, qtbot: QtBot):
        screen = seekbar.app.QApplication.primaryScreen().geometry()
        pos_x = screen.x() + 75
        pos_y = screen.y() + 75
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("window_x", pos_x)
        settings.setValue("window_y", pos_y)
        fresh_window = seekbar.app.MainWindow()
        qtbot.addWidget(fresh_window)
        assert_that(fresh_window.pos()).is_equal_to(QPoint(pos_x, pos_y))

    def test_fallback_on_offscreen_position(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("window_x", -99999)
        settings.setValue("window_y", -99999)
        loaded = window._load_window_position()
        assert_that(loaded).is_none()

    def test_fallback_on_missing_position(self, window: MainWindow):
        loaded = window._load_window_position()
        assert_that(loaded).is_none()


class TestPlaceholder:
    def test_placeholder_text(self, window: MainWindow):
        assert_that(window._search_input.placeholderText()).is_equal_to("Search all drives...")


class TestContextMenuIcons:
    def test_actions_have_icons(self, window: MainWindow):
        window._add_result("C:/test/hosts", 0)
        window.show()
        with patch.object(seekbar.app.QMenu, "popup"):
            window._show_context_menu(QPoint(10, 10))
        tray_menu = window._tray.contextMenu()
        result_menus = [menu for menu in window.findChildren(seekbar.app.QMenu) if menu is not tray_menu]
        if result_menus:
            actions = result_menus[0].actions()
            assert_that(actions).is_length(2)
            assert_that(actions[0].icon().isNull()).is_false()
            assert_that(actions[1].icon().isNull()).is_false()


class TestTintIcon:
    def test_recolors_opaque_pixmap(self, window: MainWindow):
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor("white"))
        result = window._tint_icon(QIcon(pixmap), "#FF0000")
        center = result.pixmap(QSize(16, 16)).toImage().pixelColor(8, 8)
        assert_that(center.name()).is_equal_to("#ff0000")

    def test_null_icon_returned_unchanged(self, window: MainWindow):
        empty = QIcon()
        result = window._tint_icon(empty, "#FF0000")
        assert_that(result.isNull()).is_true()


class TestInputContextMenu:
    def test_standard_menu_is_styled(self, window: MainWindow):
        with patch.object(seekbar.app.QMenu, "popup") as mock_popup:
            window._show_input_context_menu(QPoint(5, 5))
        mock_popup.assert_called_once()
        menu = window._search_input.findChild(seekbar.app.QMenu)
        assert menu is not None
        assert_that(menu.styleSheet()).contains(window._theme.surface_variant)

    def test_iconed_actions_are_tinted_others_untouched(self, window: MainWindow):
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor("white"))
        fake_menu = seekbar.app.QMenu()
        iconed = fake_menu.addAction(QIcon(pixmap), "Paste")
        plain = fake_menu.addAction("Undo")
        original_key = iconed.icon().cacheKey()

        with (
            patch.object(window._search_input, "createStandardContextMenu", return_value=fake_menu),
            patch.object(seekbar.app.QMenu, "popup"),
        ):
            window._show_input_context_menu(QPoint(5, 5))

        assert_that(iconed.icon().cacheKey()).is_not_equal_to(original_key)
        assert_that(plain.icon().isNull()).is_true()
        center = iconed.icon().pixmap(QSize(16, 16)).toImage().pixelColor(8, 8)
        assert_that(center.name()).is_equal_to(window._theme.on_surface.lower())


class TestBatchInsertion:
    def test_batch_inserts_multiple_items(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/hosts", 0, 1, False),
                ("C:/dir/hosts.txt", 1, 1, False),
                ("C:/dir/xhostsy", 4, 1, False),
            ]
        )
        assert_that(window._result_model.rowCount()).is_equal_to(3)

    def test_batch_sorted_correctly(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/xhostsy", 4, 1, False),
                ("C:/dir/hosts", 0, 1, False),
                ("C:/dir/hosts.txt", 1, 1, False),
            ]
        )
        paths = [window._result_model.path_at(i) for i in range(window._result_model.rowCount())]
        assert_that(paths).is_equal_to(["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/xhostsy"])

    def test_batch_updates_status_once(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/a.txt", 4, 1, False),
                ("C:/dir/b.txt", 4, 1, False),
                ("C:/dir/c.txt", 4, 1, False),
            ]
        )
        assert_that(window._status_label.text()).contains("3")

    def test_batch_syncs_height(self, window: MainWindow):
        window._add_results_batch([("C:/dir/a.txt", 4, 1, False)])
        item_h = window._delegate.item_height
        expected = window._search_height + 1 + item_h + window._RADIUS + window._MARGIN * 2
        assert_that(window.height()).is_equal_to(expected)

    def test_batch_ignored_without_worker(self, window: MainWindow):
        window._worker = None
        window._add_results_batch([("C:/dir/a.txt", 4, 1, False)])
        assert_that(window._result_model.rowCount()).is_equal_to(0)

    def test_batch_empty_list_noop(self, window: MainWindow):
        window._add_results_batch([])
        assert_that(window._result_model.rowCount()).is_equal_to(0)
        assert_that(window._status_label.text()).is_empty()

    def test_batch_preserves_is_dir(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/folder", 4, 1, True),
                ("C:/dir/file.txt", 4, 1, False),
            ]
        )
        assert_that(window._result_model.data(window._result_model.index(0), _IS_DIR_ROLE)).is_true()
        assert_that(window._result_model.data(window._result_model.index(1), _IS_DIR_ROLE)).is_false()

    def test_multiple_batches_merge_correctly(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/hosts", 0, 1, False),
                ("C:/dir/xhostsy", 4, 1, False),
            ]
        )
        window._add_results_batch(
            [
                ("C:/dir/hosts.txt", 1, 1, False),
                ("C:/dir/myhosts", 3, 1, False),
            ]
        )
        paths = [window._result_model.path_at(i) for i in range(window._result_model.rowCount())]
        assert_that(paths).is_equal_to(["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/myhosts", "C:/dir/xhostsy"])


class TestExtendedNavigation:
    def test_page_down(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._select_row(0)
        qtbot.keyClick(window, Qt.Key.Key_PageDown)
        assert_that(window._current_row()).is_equal_to(window._MAX_VISIBLE)

    def test_page_up(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._select_row(15)
        qtbot.keyClick(window, Qt.Key.Key_PageUp)
        assert_that(window._current_row()).is_equal_to(15 - window._MAX_VISIBLE)

    def test_page_down_clamps_to_last(self, window: MainWindow, qtbot: QtBot):
        for i in range(5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._select_row(3)
        qtbot.keyClick(window, Qt.Key.Key_PageDown)
        assert_that(window._current_row()).is_equal_to(4)

    def test_page_up_clamps_to_first(self, window: MainWindow, qtbot: QtBot):
        for i in range(5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._select_row(1)
        qtbot.keyClick(window, Qt.Key.Key_PageUp)
        assert_that(window._current_row()).is_equal_to(0)

    def test_home_jumps_to_first(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._select_row(15)
        qtbot.keyClick(window, Qt.Key.Key_Home)
        assert_that(window._current_row()).is_equal_to(0)

    def test_end_jumps_to_last(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._select_row(0)
        qtbot.keyClick(window, Qt.Key.Key_End)
        assert_that(window._current_row()).is_equal_to(19)


class TestSearchingAnimation:
    def test_start_sets_initial_text(self, window: MainWindow):
        window._start_searching_animation()
        assert_that(window._status_label.text()).is_equal_to("searching.")
        assert_that(window._searching_timer.isActive()).is_true()

    def test_stop_stops_timer(self, window: MainWindow):
        window._start_searching_animation()
        window._stop_searching_animation()
        assert_that(window._searching_timer.isActive()).is_false()

    def test_cycle_one_to_two(self, window: MainWindow):
        window._status_label.setText("searching.")
        window._animate_searching()
        assert_that(window._status_label.text()).is_equal_to("searching..")

    def test_cycle_two_to_three(self, window: MainWindow):
        window._status_label.setText("searching..")
        window._animate_searching()
        assert_that(window._status_label.text()).is_equal_to("searching...")

    def test_cycle_three_to_one(self, window: MainWindow):
        window._status_label.setText("searching...")
        window._animate_searching()
        assert_that(window._status_label.text()).is_equal_to("searching.")

    def test_clear_text_stops_animation(self, window: MainWindow):
        window._search_input.setText("query")
        assert_that(window._searching_timer.isActive()).is_true()
        window._search_input.setText("")
        assert_that(window._searching_timer.isActive()).is_false()

    def test_batch_stops_animation(self, window: MainWindow):
        window._start_searching_animation()
        assert_that(window._searching_timer.isActive()).is_true()
        window._add_results_batch([("C:/dir/a.txt", 4, 1, False)])
        assert_that(window._searching_timer.isActive()).is_false()

    def test_search_done_stops_animation(self, window: MainWindow):
        window._start_searching_animation()
        assert_that(window._searching_timer.isActive()).is_true()
        window._on_search_done(0)
        assert_that(window._searching_timer.isActive()).is_false()


class TestErrorFeedback:
    def test_open_file_failure(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        mock_desktop = MagicMock()
        mock_desktop.openUrl.return_value = False
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_file_by_path("C:/nonexistent/file.txt")
        assert_that(window._status_label.text()).is_equal_to("Failed to open file")

    def test_open_folder_oserror(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(seekbar.app.subprocess, "run", MagicMock(side_effect=OSError))
        window._open_folder("C:/test/hosts")
        assert_that(window._status_label.text()).is_equal_to("Failed to open folder")

    def test_open_folder_linux_failure(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        mock_desktop = MagicMock()
        mock_desktop.openUrl.return_value = False
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_folder("/home/test/file.txt")
        assert_that(window._status_label.text()).is_equal_to("Failed to open folder")


class TestTempStatus:
    def test_shows_message(self, window: MainWindow):
        window._show_temp_status("Error occurred")
        assert_that(window._status_label.text()).is_equal_to("Error occurred")

    def test_restore_with_results(self, window: MainWindow):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._show_temp_status("Error")
        window._restore_status()
        assert_that(window._status_label.text()).contains("2")

    def test_restore_without_results(self, window: MainWindow):
        window._show_temp_status("Error")
        window._restore_status()
        assert_that(window._status_label.text()).is_empty()


class TestHelpPopup:
    def test_initially_hidden(self, window: MainWindow):
        assert_that(window._help_popup.isHidden()).is_true()

    def test_toggle_shows(self, window: MainWindow):
        window._toggle_help()
        assert_that(window._help_popup.isHidden()).is_false()

    def test_toggle_twice_hides(self, window: MainWindow):
        window._toggle_help()
        window._toggle_help()
        assert_that(window._help_popup.isHidden()).is_true()

    def test_f1_key_toggles(self, window: MainWindow, qtbot: QtBot):
        qtbot.keyClick(window, Qt.Key.Key_F1)
        assert_that(window._help_popup.isHidden()).is_false()

    def test_text_change_hides_help(self, window: MainWindow):
        window._toggle_help()
        assert_that(window._help_popup.isHidden()).is_false()
        window._search_input.setText("query")
        assert_that(window._help_popup.isHidden()).is_true()

    def test_hide_popups_when_visible(self, window: MainWindow):
        window._toggle_help()
        window._hide_popups()
        assert_that(window._help_popup.isHidden()).is_true()

    def test_hide_popups_when_already_hidden(self, window: MainWindow):
        window._hide_popups()
        assert_that(window._help_popup.isHidden()).is_true()

    def test_help_content(self, window: MainWindow):
        html = window._help_popup.text()
        assert_that(html).contains("Esc")
        assert_that(html).contains("Ctrl+Q")
        assert_that(html).contains("F1")
        assert_that(html).contains("<table")

    def test_help_html_uneven_groups(self, window: MainWindow):
        shortcuts = (
            (("A",), "First"),
            None,
            (("B",), "Second"),
            (("C",), "Third"),
        )
        with patch("seekbar.app._HELP_SHORTCUTS", shortcuts):
            html = window._help_html()
        assert_that(html).contains("<td></td><td></td>")

    def test_help_updates_on_theme_switch(self, window: MainWindow):
        old_html = window._help_popup.text()
        window._set_theme(LIGHT_THEME)
        new_html = window._help_popup.text()
        assert_that(old_html).is_not_equal_to(new_html)

    def test_sync_height_with_help(self, window: MainWindow):
        window._toggle_help()
        help_height = window._help_popup.sizeHint().height()
        expected = window._search_height + 1 + help_height + window._RADIUS + window._MARGIN * 2
        assert_that(window._height_target).is_equal_to(expected)
        window._finalize_height()
        assert_that(window.height()).is_equal_to(expected)

    def test_help_hides_results_list(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        window._toggle_help()
        assert_that(window._result_list.isHidden()).is_true()
        assert_that(window._separator.isHidden()).is_false()

    def test_help_shows_separator_without_results(self, window: MainWindow):
        window._toggle_help()
        assert_that(window._separator.isHidden()).is_false()
        assert_that(window._result_list.isHidden()).is_true()

    def test_batch_skips_sync_when_help_open(self, window: MainWindow):
        window._toggle_help()
        window._finalize_height()
        height_before = window.height()
        window._add_result("C:/test/file.txt", 4)
        assert_that(window.height()).is_equal_to(height_before)

    def test_done_skips_sync_when_help_open(self, window: MainWindow):
        window._toggle_help()
        window._finalize_height()
        height_before = window.height()
        window._on_search_done(0)
        assert_that(window.height()).is_equal_to(height_before)

    def test_typing_with_help_animates_collapse(self, window: MainWindow):
        window._toggle_help()
        window._finalize_height()
        window._search_input.setText("query")
        window._finalize_height()
        expected = window._search_height + window._MARGIN * 2
        assert_that(window.height()).is_equal_to(expected)
        assert_that(window._help_popup.isHidden()).is_true()

    def test_clear_text_with_help_animates_collapse(self, window: MainWindow):
        window._search_input.setText("query")
        window._toggle_help()
        window._finalize_height()
        window._search_input.setText("")
        window._finalize_height()
        expected = window._search_height + window._MARGIN * 2
        assert_that(window.height()).is_equal_to(expected)
        assert_that(window._help_popup.isHidden()).is_true()


class TestDonatePopup:
    def test_f3_toggles_donate_popup(self, window: MainWindow, qtbot):
        assert_that(window._donate_popup.isHidden()).is_true()
        qtbot.keyClick(window, Qt.Key.Key_F3)
        assert_that(window._donate_popup.isHidden()).is_false()
        qtbot.keyClick(window, Qt.Key.Key_F3)
        assert_that(window._donate_popup.isHidden()).is_true()

    def test_f2_hides_help(self, window: MainWindow):
        window._toggle_help()
        assert_that(window._help_popup.isHidden()).is_false()
        window._toggle_donate()
        assert_that(window._help_popup.isHidden()).is_true()
        assert_that(window._donate_popup.isHidden()).is_false()

    def test_f1_hides_donate(self, window: MainWindow):
        window._toggle_donate()
        assert_that(window._donate_popup.isHidden()).is_false()
        window._toggle_help()
        assert_that(window._donate_popup.isHidden()).is_true()
        assert_that(window._help_popup.isHidden()).is_false()

    def test_donate_content(self, window: MainWindow):
        html = window._donate_popup.text()
        assert_that(html).contains("GitHub")
        assert_that(html).contains("DonationAlerts")
        assert_that(html).contains("Boosty")
        assert_that(html).contains("TON")
        assert_that(html).contains("USDT")

    def test_donate_link_opens_url(self, window: MainWindow):
        with patch("seekbar.app.QDesktopServices.openUrl") as mock_open:
            window._on_donate_link("https://boosty.to/solganis")
        mock_open.assert_called_once()

    def test_donate_copy_to_clipboard(self, window: MainWindow):
        address = "UQAZDskr7UZE9Hn8Q8asCfmYIsicgL0KS9YNvRJ5NF53OPPo"
        window._on_donate_link(f"copy:{address}")
        assert_that(seekbar.app.QApplication.clipboard().text()).is_equal_to(address)
        assert_that(window._status_label.text()).is_equal_to("Copied!")

    def test_donate_updates_on_theme_switch(self, window: MainWindow):
        old_html = window._donate_popup.text()
        window._set_theme(LIGHT_THEME)
        new_html = window._donate_popup.text()
        assert_that(old_html).is_not_equal_to(new_html)

    def test_text_change_hides_donate(self, window: MainWindow):
        window._toggle_donate()
        assert_that(window._donate_popup.isHidden()).is_false()
        window._search_input.setText("query")
        assert_that(window._donate_popup.isHidden()).is_true()

    def test_hide_popups_hides_donate(self, window: MainWindow):
        window._toggle_donate()
        window._hide_popups()
        assert_that(window._donate_popup.isHidden()).is_true()

    def test_set_height_restores_position(self, window: MainWindow):
        original_pos = QPoint(100, 200)
        window.move(original_pos)
        shifted_pos = QPoint(100, 0)
        original_set_fixed = MainWindow.setFixedHeight

        def shifting_set_fixed(self_widget, height):
            original_set_fixed(self_widget, height)
            self_widget.move(shifted_pos)

        with patch.object(MainWindow, "setFixedHeight", shifting_set_fixed):
            window._set_height_preserving_pos(300)
        assert_that(window.pos()).is_equal_to(original_pos)

    def test_sync_height_with_donate(self, window: MainWindow):
        window._toggle_donate()
        donate_height = window._donate_popup.sizeHint().height()
        expected = window._search_height + 1 + donate_height + window._RADIUS + window._MARGIN * 2
        assert_that(window._height_target).is_equal_to(expected)
        window._finalize_height()
        assert_that(window.height()).is_equal_to(expected)


class TestSettings:
    def test_load_accent(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("accent", "blue")
        assert_that(window._load_accent()).is_equal_to("blue")
        settings.setValue("accent", "does-not-exist")
        assert_that(window._load_accent()).is_equal_to(DEFAULT_ACCENT)
        settings.setValue("accent", 123)
        assert_that(window._load_accent()).is_equal_to(DEFAULT_ACCENT)

    def test_load_tray_icon_mode(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("tray_icon_mode", "white")
        assert_that(window._load_tray_icon_mode()).is_equal_to(TrayIconMode.WHITE)
        settings.setValue("tray_icon_mode", "bogus")
        assert_that(window._load_tray_icon_mode()).is_equal_to(TrayIconMode.AUTO)

    def test_icon_color_modes(self, window: MainWindow):
        window._theme = DARK_THEME
        window._tray_icon_mode = TrayIconMode.WHITE
        assert_that(window._icon_color()).is_equal_to("#FFFFFF")
        window._tray_icon_mode = TrayIconMode.BLACK
        assert_that(window._icon_color()).is_equal_to("#000000")
        window._tray_icon_mode = TrayIconMode.ACCENT
        assert_that(window._icon_color()).is_equal_to(DARK_THEME.primary)
        window._tray_icon_mode = TrayIconMode.AUTO
        assert_that(window._icon_color()).is_equal_to(DARK_THEME.on_surface)

    def test_set_accent_noop(self, window: MainWindow):
        window._set_accent(window._accent_id)
        assert_that(window._accent_id).is_equal_to(DEFAULT_ACCENT)

    def test_set_tray_icon_mode_noop(self, window: MainWindow):
        window._set_tray_icon_mode(window._tray_icon_mode)
        assert_that(window._tray_icon_mode).is_equal_to(TrayIconMode.AUTO)

    def test_settings_popup_hidden_initially(self, window: MainWindow):
        assert_that(window._settings_popup.isHidden()).is_true()

    def test_accent_buttons_built_and_active_checked(self, window: MainWindow):
        assert_that(window._accent_buttons).is_length(len(ACCENTS))
        checked = [accent_id for accent_id, button in window._accent_buttons.items() if button.isChecked()]
        assert_that(checked).is_equal_to([DEFAULT_ACCENT])

    def test_tray_buttons_built_and_active_checked(self, window: MainWindow):
        assert_that(window._tray_buttons).is_length(4)
        checked = [mode for mode, button in window._tray_buttons.items() if button.isChecked()]
        assert_that(checked).is_equal_to([TrayIconMode.AUTO])

    def test_accent_button_click_changes_accent(self, window: MainWindow):
        window._theme_mode = ThemeMode.DARK
        window._accent_buttons["blue"].click()
        assert_that(window._accent_id).is_equal_to("blue")
        assert_that(window._theme.primary).is_equal_to(ACCENTS["blue"].primary_dark)
        assert_that(window._load_accent()).is_equal_to("blue")
        assert_that(window._accent_buttons["blue"].isChecked()).is_true()

    def test_tray_button_click_changes_mode(self, window: MainWindow):
        old_key = window._tray.icon().cacheKey()
        window._tray_buttons[TrayIconMode.WHITE].click()
        assert_that(window._tray_icon_mode).is_equal_to(TrayIconMode.WHITE)
        assert_that(window._tray.icon().cacheKey()).is_not_equal_to(old_key)
        assert_that(window._load_tray_icon_mode()).is_equal_to(TrayIconMode.WHITE)
        assert_that(window._tray_buttons[TrayIconMode.WHITE].isChecked()).is_true()

    def test_accent_swatch_style_matches_theme(self, window: MainWindow):
        window._set_theme(LIGHT_THEME)
        qss = window._accent_buttons["blue"].styleSheet()
        assert_that(qss).contains(ACCENTS["blue"].primary_light)
        assert_that(qss).contains(ACCENTS["blue"].selected_light)
        window._set_theme(DARK_THEME)
        qss = window._accent_buttons["blue"].styleSheet()
        assert_that(qss).contains(ACCENTS["blue"].primary_dark)
        assert_that(qss).contains(ACCENTS["blue"].selected_dark)

    def test_f2_toggles_settings_popup(self, window: MainWindow, qtbot: QtBot):
        assert_that(window._settings_popup.isHidden()).is_true()
        qtbot.keyClick(window, Qt.Key.Key_F2)
        assert_that(window._settings_popup.isHidden()).is_false()
        qtbot.keyClick(window, Qt.Key.Key_F2)
        assert_that(window._settings_popup.isHidden()).is_true()

    def test_settings_hides_other_popups(self, window: MainWindow):
        window._toggle_help()
        window._toggle_settings()
        assert_that(window._help_popup.isHidden()).is_true()
        assert_that(window._settings_popup.isHidden()).is_false()

    def test_help_hides_settings_popup(self, window: MainWindow):
        window._toggle_settings()
        window._toggle_help()
        assert_that(window._settings_popup.isHidden()).is_true()
        assert_that(window._help_popup.isHidden()).is_false()

    def test_sync_height_with_settings(self, window: MainWindow):
        window._toggle_settings()
        settings_height = window._settings_popup.sizeHint().height()
        expected = window._search_height + 1 + settings_height + window._RADIUS + window._MARGIN * 2
        assert_that(window._height_target).is_equal_to(expected)
        window._finalize_height()
        assert_that(window.height()).is_equal_to(expected)

    def test_typing_dismisses_settings_popup(self, window: MainWindow):
        window._toggle_settings()
        window._search_input.setText("query")
        assert_that(window._settings_popup.isHidden()).is_true()


class TestSystemTray:
    def test_tray_exists(self, window: MainWindow):
        assert_that(window._tray).is_instance_of(QSystemTrayIcon)

    def test_tray_tooltip(self, window: MainWindow):
        assert_that(window._tray.toolTip()).is_equal_to("Seekbar")

    def test_tray_context_menu_actions(self, window: MainWindow):
        menu = window._tray.contextMenu()
        actions = menu.actions()
        assert_that(actions).is_length(3)
        assert_that(actions[0].text()).is_equal_to("Show / Hide")
        assert_that(actions[1].text()).is_equal_to("Launch at startup")
        assert_that(actions[2].text()).is_equal_to("Quit")

    def test_autostart_action_checkable_reflects_state(self, window: MainWindow):
        assert_that(window._autostart_action.isCheckable()).is_true()

    def test_autostart_toggle_calls_backend(self, window: MainWindow):
        with patch.object(seekbar.app.autostart, "set_enabled") as mock_set:
            window._autostart_action.setChecked(False)
            mock_set.reset_mock()
            window._autostart_action.setChecked(True)
            mock_set.assert_called_once_with(True)

    @staticmethod
    def _window_with_autostart(qtbot: QtBot, *, registered: bool) -> MainWindow:
        with (
            patch("seekbar.app._hotkey") as mock_hk,
            patch.object(seekbar.app.autostart, "is_enabled", return_value=registered),
        ):
            mock_hk.register_hotkey.return_value = False
            win = MainWindow()
        qtbot.addWidget(win)
        return win

    def test_autostart_off_by_default_when_not_registered(self, qtbot: QtBot):
        win = self._window_with_autostart(qtbot, registered=False)
        try:
            assert_that(win._autostart_action.isChecked()).is_false()
        finally:
            win._tray.hide()

    def test_autostart_reflects_existing_registration(self, qtbot: QtBot):
        win = self._window_with_autostart(qtbot, registered=True)
        try:
            assert_that(win._autostart_action.isChecked()).is_true()
        finally:
            win._tray.hide()

    def test_tray_menu_styled_at_startup(self, window: MainWindow):
        style = window._tray.contextMenu().styleSheet()
        assert_that(style).contains("QMenu")
        assert_that(style).contains(window._theme.surface_variant)

    def test_tray_menu_restyled_on_theme_change(self, window: MainWindow):
        window._set_theme(LIGHT_THEME)
        assert_that(window._tray.contextMenu().styleSheet()).contains(LIGHT_THEME.surface_variant)

    def test_close_hides_to_tray(self, window: MainWindow):
        window.show()
        window.close()
        assert_that(window.isVisible()).is_false()
        assert_that(window._tray.isVisible()).is_true()

    def test_close_saves_position(self, window: MainWindow):
        window.show()
        window.move(100, 200)
        window.close()
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        assert_that(settings.value("window_x")).is_not_none()

    def test_tray_double_click_shows(self, window: MainWindow):
        window.hide()
        window._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
        assert_that(window.isVisible()).is_true()

    def test_tray_double_click_hides(self, window: MainWindow):
        window.show()
        window._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
        assert_that(window.isVisible()).is_false()

    def test_tray_single_click_ignored(self, window: MainWindow):
        window.show()
        window._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        assert_that(window.isVisible()).is_true()

    def test_tray_icon_updates_on_theme(self, window: MainWindow):
        old_key = window._tray.icon().cacheKey()
        window._set_theme(LIGHT_THEME)
        assert_that(window._tray.icon().cacheKey()).is_not_equal_to(old_key)

    def test_quit_from_tray(self, window: MainWindow):
        with patch.object(seekbar.app.QApplication, "quit") as mock_quit:
            window._quit_app()
        mock_quit.assert_called_once()

    def test_quit_hides_tray(self, window: MainWindow):
        with patch.object(seekbar.app.QApplication, "quit"):
            window._quit_app()
        assert_that(window._tray.isVisible()).is_false()


class TestToggleVisibility:
    def test_show_from_hidden(self, window: MainWindow):
        window.hide()
        window._toggle_visibility()
        assert_that(window.isVisible()).is_true()

    def test_hide_from_visible(self, window: MainWindow):
        window.show()
        window._toggle_visibility()
        assert_that(window.isVisible()).is_false()

    def test_show_selects_all_text(self, window: MainWindow):
        window.hide()
        window._search_input.setText("query")
        window._toggle_visibility()
        assert_that(window._search_input.selectedText()).is_equal_to("query")


class TestAltDrag:
    def test_alt_click_starts_drag(self, window: MainWindow):
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(110, 110),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
        )
        assert_that(window.eventFilter(window._search_input, event)).is_true()
        assert_that(window._drag_pos).is_not_none()

    def test_non_alt_click_passes_through(self, window: MainWindow):
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(110, 110),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        assert_that(window.eventFilter(window._search_input, event)).is_false()

    def test_alt_click_on_other_widget_passes_through(self, window: MainWindow):
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(110, 110),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
        )
        assert_that(window.eventFilter(window._status_label, event)).is_false()

    def test_mouse_move_during_drag(self, window: MainWindow):
        window._drag_pos = QPoint(10, 10)
        move_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(20, 20),
            QPointF(120, 120),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
        )
        assert_that(window.eventFilter(window._search_input, move_event)).is_true()

    def test_mouse_move_without_button_does_not_drag(self, window: MainWindow):
        # A stale drag offset must not let plain cursor movement (no button) fling the window.
        window._drag_pos = QPoint(10, 10)
        before = window.pos()
        move_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(20, 20),
            QPointF(120, 120),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        assert_that(window.eventFilter(window._search_input, move_event)).is_false()
        assert_that(window.pos()).is_equal_to(before)

    def test_mouse_release_ends_drag(self, window: MainWindow):
        window._drag_pos = QPoint(10, 10)
        release_event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(20, 20),
            QPointF(120, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        assert_that(window.eventFilter(window._search_input, release_event)).is_true()
        assert_that(window._drag_pos).is_none()


class TestGlobalHotkey:
    def test_hotkey_not_registered_by_default(self, window: MainWindow):
        assert_that(window._hotkey_registered).is_false()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only _HotkeyFilter")
    def test_hotkey_registers_on_init(self, qtbot: QtBot):
        with patch("seekbar.app._hotkey") as mock_hk:
            mock_hk.register_hotkey.return_value = True
            mock_hk.WM_HOTKEY = 0x0312
            main_window = MainWindow()
        qtbot.addWidget(main_window)
        assert_that(main_window._hotkey_registered).is_true()
        assert_that(main_window._hotkey_filter).is_not_none()
        main_window._tray.hide()

    def test_hotkey_registers_via_macos_backend(self, qtbot: QtBot):
        mock_mac = MagicMock()
        mock_mac.register_hotkey.return_value = True
        with patch("seekbar.app._hotkey", None), patch("seekbar.app._hotkey_mac", mock_mac):
            main_window = MainWindow()
        qtbot.addWidget(main_window)
        try:
            mock_mac.register_hotkey.assert_called_once()
            assert_that(main_window._hotkey_registered).is_true()
        finally:
            main_window._tray.hide()

    def test_quit_unregisters_macos_hotkey(self, qtbot: QtBot):
        mock_mac = MagicMock()
        mock_mac.register_hotkey.return_value = True
        with patch("seekbar.app._hotkey", None), patch("seekbar.app._hotkey_mac", mock_mac):
            main_window = MainWindow()
            qtbot.addWidget(main_window)
            with patch.object(seekbar.app.QApplication, "quit"):
                main_window._quit_app()
        mock_mac.unregister_hotkey.assert_called_once()

    def test_no_filter_on_registration_failure(self, window: MainWindow):
        assert_that(window._hotkey_filter).is_none()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only _HotkeyFilter")
    def test_filter_triggers_toggle(self, window: MainWindow):
        window.show()
        callback = MagicMock()
        # noinspection PyProtectedMember
        hotkey_filter = seekbar.app._HotkeyFilter(callback)
        msg = ctypes.wintypes.MSG()
        msg.message = 0x0312
        result = hotkey_filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
        assert_that(result).is_equal_to((True, 0))
        callback.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only _HotkeyFilter")
    def test_filter_ignores_other_messages(self):
        callback = MagicMock()
        # noinspection PyProtectedMember
        hotkey_filter = seekbar.app._HotkeyFilter(callback)
        msg = ctypes.wintypes.MSG()
        msg.message = 0x0001
        result = hotkey_filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
        assert_that(result).is_equal_to((False, 0))
        callback.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only _HotkeyFilter")
    def test_filter_ignores_non_windows_events(self):
        callback = MagicMock()
        # noinspection PyProtectedMember
        hotkey_filter = seekbar.app._HotkeyFilter(callback)
        result = hotkey_filter.nativeEventFilter(b"xcb_generic_event_t", 0)
        assert_that(result).is_equal_to((False, 0))
        callback.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only _HotkeyFilter")
    def test_quit_unregisters_hotkey(self, qtbot: QtBot):
        with patch("seekbar.app._hotkey") as mock_hk:
            mock_hk.register_hotkey.return_value = True
            mock_hk.WM_HOTKEY = 0x0312
            main_window = MainWindow()
            qtbot.addWidget(main_window)
            with patch.object(seekbar.app.QApplication, "quit"):
                main_window._quit_app()
            mock_hk.unregister_hotkey.assert_called_once()
            main_window._tray.hide()

    def test_hotkey_skipped_when_no_module(self, window: MainWindow):
        with patch("seekbar.app._hotkey", None):
            window._init_hotkey()
        assert_that(window._hotkey_registered).is_false()


class TestResultModel:
    @pytest.fixture
    def model(self) -> _ResultModel:
        instance = _ResultModel(_RecencyStore())
        instance.add_batch([("C:/dir/file.txt", 0, 0, False)])
        return instance

    def test_data_invalid_index_returns_none(self, model: _ResultModel):
        assert_that(model.data(QModelIndex(), Qt.ItemDataRole.UserRole)).is_none()

    def test_data_user_role_returns_path(self, model: _ResultModel):
        assert_that(model.data(model.index(0), Qt.ItemDataRole.UserRole)).is_equal_to("C:/dir/file.txt")

    def test_data_unknown_role_returns_none(self, model: _ResultModel):
        assert_that(model.data(model.index(0), Qt.ItemDataRole.DisplayRole)).is_none()

    def test_data_name_role_returns_basename(self, model: _ResultModel):
        assert_that(model.data(model.index(0), _NAME_ROLE)).is_equal_to("file.txt")

    def test_data_parent_role_returns_parent_name(self, model: _ResultModel):
        assert_that(model.data(model.index(0), _PARENT_ROLE)).is_equal_to("dir")

    def test_row_count_with_valid_parent_is_zero(self, model: _ResultModel):
        assert_that(model.rowCount(model.index(0))).is_equal_to(0)

    def test_recency_breaks_score_tie(self):
        recency = _RecencyStore()
        recency.record("C:/dir/b.txt")
        model = _ResultModel(recency)
        model.add_batch([("C:/dir/a.txt", 4, 1, False), ("C:/dir/b.txt", 4, 1, False)])
        assert_that(model.path_at(0)).is_equal_to("C:/dir/b.txt")
        assert_that(model.path_at(1)).is_equal_to("C:/dir/a.txt")


class TestRecencyStore:
    def test_empty_history_ranks_at_limit(self):
        assert_that(_RecencyStore().rank("C:/x")).is_equal_to(_RecencyStore._LIMIT)

    def test_record_then_rank_is_zero(self):
        store = _RecencyStore()
        store.record("C:/a")
        assert_that(store.rank("C:/a")).is_equal_to(0)

    def test_record_moves_existing_to_front(self):
        store = _RecencyStore()
        store.record("C:/a")
        store.record("C:/b")
        assert_that(store.rank("C:/a")).is_equal_to(1)
        store.record("C:/a")
        assert_that(store.rank("C:/a")).is_equal_to(0)
        assert_that(store.rank("C:/b")).is_equal_to(1)

    def test_record_same_path_twice_is_noop(self):
        store = _RecencyStore()
        store.record("C:/a")
        store.record("C:/a")
        assert_that(store.rank("C:/a")).is_equal_to(0)

    def test_persists_across_instances(self):
        _RecencyStore().record("C:/a")
        assert_that(_RecencyStore().rank("C:/a")).is_equal_to(0)

    def test_non_string_raw_is_ignored(self):
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("recent_paths", 123)
        assert_that(_RecencyStore().rank("C:/a")).is_equal_to(_RecencyStore._LIMIT)

    def test_invalid_json_is_ignored(self):
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("recent_paths", "not json{")
        assert_that(_RecencyStore().rank("C:/a")).is_equal_to(_RecencyStore._LIMIT)

    def test_non_list_json_is_ignored(self):
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("recent_paths", '{"x": 1}')
        assert_that(_RecencyStore().rank("C:/a")).is_equal_to(_RecencyStore._LIMIT)

    def test_non_string_items_are_filtered(self):
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("recent_paths", '["C:/a", 5]')
        assert_that(_RecencyStore().rank("C:/a")).is_equal_to(0)

    def test_truncates_at_limit(self):
        paths = [f"C:/p{i}" for i in range(_RecencyStore._LIMIT)]
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("recent_paths", json.dumps(paths))
        store = _RecencyStore()
        store.record("C:/new")
        assert_that(store.rank("C:/new")).is_equal_to(0)
        assert_that(store.rank("C:/p499")).is_equal_to(_RecencyStore._LIMIT)


class TestRecencyStoreProperties:
    @hypothesis_settings(deadline=None, max_examples=50)
    @given(st.lists(st.text(max_size=8), min_size=1, max_size=15))
    def test_last_recorded_is_rank_zero(self, paths: list[str]):
        QSettings(SETTINGS_ORG, SETTINGS_APP).clear()
        store = _RecencyStore()
        for path in paths:
            store.record(path)
        assert_that(store.rank(paths[-1])).is_equal_to(0)

    @hypothesis_settings(deadline=None, max_examples=50)
    @given(st.lists(st.text(max_size=8), max_size=15))
    def test_ranks_stay_bounded(self, paths: list[str]):
        QSettings(SETTINGS_ORG, SETTINGS_APP).clear()
        store = _RecencyStore()
        for path in paths:
            store.record(path)
        for path in paths:
            assert_that(store.rank(path)).is_between(0, _RecencyStore._LIMIT)

    @hypothesis_settings(deadline=None, max_examples=50)
    @given(st.lists(st.text(max_size=8), max_size=15))
    def test_no_duplicate_paths(self, paths: list[str]):
        QSettings(SETTINGS_ORG, SETTINGS_APP).clear()
        store = _RecencyStore()
        for path in paths:
            store.record(path)
        assert_that(store._paths).does_not_contain_duplicates()


_PATH_SEGMENT = st.text(alphabet="abcABC123._-", min_size=1, max_size=8).filter(
    lambda segment: segment not in (".", "..")
)


@st.composite
def _result_path(draw: st.DrawFn) -> str:
    segments = draw(st.lists(_PATH_SEGMENT, min_size=1, max_size=5))
    path = segments[0]
    for segment in segments[1:]:
        path += draw(st.sampled_from(["\\", "/"])) + segment
    return path


class TestBasenameLengthProperties:
    @given(_result_path())
    def test_matches_pure_windows_path_name(self, path: str):
        # Both treat "\\" and "/" as separators on every OS, so the property is platform-independent.
        assert_that(_basename_length(path)).is_equal_to(len(PureWindowsPath(path).name))


_RESULTS = st.lists(
    st.tuples(
        st.text(max_size=12),
        st.integers(min_value=0, max_value=5),
        st.integers(min_value=0, max_value=10),
        st.booleans(),
    ),
    max_size=20,
)


def _ordered_paths(model: _ResultModel) -> list[str]:
    return [model.path_at(row) for row in range(model.rowCount())]


def _record_insert_spans(model: _ResultModel) -> list[int]:
    spans: list[int] = []
    model.rowsInserted.connect(lambda _parent, first, last: spans.append(last - first + 1))
    return spans


class TestResultModelMerge:
    def test_empty_model_batch_is_single_run(self):
        model = _ResultModel(_RecencyStore())
        spans = _record_insert_spans(model)
        model.add_batch([("C:/d/a.txt", 0, 1, False), ("C:/d/b.txt", 2, 1, False), ("C:/d/c.txt", 4, 1, False)])
        # An empty model has no existing rows to split the batch, so it inserts as one contiguous run.
        assert_that(spans).is_equal_to([3])

    def test_run_grouping_emits_fewer_runs_than_items(self):
        model = _ResultModel(_RecencyStore())
        model.add_batch([("C:/d/s0.txt", 0, 1, False), ("C:/d/s2.txt", 2, 1, False), ("C:/d/s4.txt", 4, 1, False)])
        spans = _record_insert_spans(model)
        # Two score-1 items land contiguously between the existing 0 and 2; the score-3 item is a
        # separate run between 2 and 4. So three items merge as two runs, not three.
        model.add_batch([("C:/d/x1.txt", 1, 1, False), ("C:/d/y1.txt", 1, 1, False), ("C:/d/z3.txt", 3, 1, False)])
        assert_that(spans).is_equal_to([2, 1])
        assert_that(_ordered_paths(model)).is_equal_to(
            ["C:/d/s0.txt", "C:/d/x1.txt", "C:/d/y1.txt", "C:/d/s2.txt", "C:/d/z3.txt", "C:/d/s4.txt"],
        )

    def test_interleaved_items_emit_one_run_each(self):
        model = _ResultModel(_RecencyStore())
        model.add_batch([("C:/d/s0.txt", 0, 1, False), ("C:/d/s2.txt", 2, 1, False), ("C:/d/s4.txt", 4, 1, False)])
        spans = _record_insert_spans(model)
        # Each batch item falls into a distinct gap, so every item is its own run.
        model.add_batch([("C:/d/a1.txt", 1, 1, False), ("C:/d/b3.txt", 3, 1, False)])
        assert_that(spans).is_equal_to([1, 1])
        assert_that(_ordered_paths(model)).is_equal_to(
            ["C:/d/s0.txt", "C:/d/a1.txt", "C:/d/s2.txt", "C:/d/b3.txt", "C:/d/s4.txt"],
        )

    def test_row_count_matches_total_across_batches(self):
        model = _ResultModel(_RecencyStore())
        model.add_batch([("C:/d/a.txt", 0, 1, False), ("C:/d/b.txt", 3, 1, False)])
        model.add_batch([("C:/d/c.txt", 1, 1, False)])
        model.add_batch([("C:/d/d.txt", 5, 1, False), ("C:/d/e.txt", 2, 1, False), ("C:/d/f.txt", 4, 1, False)])
        assert_that(model.rowCount()).is_equal_to(6)
        assert_that(model._keys).is_sorted()

    def test_scale_emits_one_run_per_batch(self):
        model = _ResultModel(_RecencyStore())
        spans = _record_insert_spans(model)
        # 100 batches of 100 key-identical rows: each batch appends as a single run, so the old
        # per-item signal storm (10_000 emissions) collapses to one emission per batch.
        for batch_index in range(100):
            model.add_batch([(f"C:/d/{batch_index:03d}{item:03d}.txt", 0, 1, False) for item in range(100)])
        assert_that(model.rowCount()).is_equal_to(10_000)
        assert_that(len(spans)).is_equal_to(100)
        assert_that(model._keys).is_sorted()


class TestResultModelProperties:
    @hypothesis_settings(max_examples=50)
    @given(_RESULTS)
    def test_keys_stay_sorted(self, results):
        model = _ResultModel(_RecencyStore())
        model.add_batch(results)
        assert_that(model._keys).is_sorted()

    @hypothesis_settings(max_examples=50)
    @given(st.lists(_RESULTS, max_size=6))
    def test_sequence_of_batches_stays_sorted_and_aligned(self, batches: list[list[tuple[str, int, int, bool]]]):
        model = _ResultModel(_RecencyStore())
        expected: list[tuple[tuple[int, int, int, int], str]] = []
        for batch in batches:
            model.add_batch(batch)
            for path, score, depth, _is_dir in batch:
                # Empty recency ranks every path at _LIMIT, so the key is fully determined here.
                expected.append(((score, _RecencyStore._LIMIT, depth, _basename_length(path)), path))
        assert_that(model._keys).is_sorted()
        assert_that(len(model._rows)).is_equal_to(len(model._keys))
        # Rows must stay aligned with keys: a stable sort of (key, path) reproduces the row order.
        assert_that(_ordered_paths(model)).is_equal_to([path for _key, path in sorted(expected, key=lambda kp: kp[0])])


class TestVersionFlag:
    def test_long_flag_prints_version(self, capsys):
        handled = _handle_version_flag(["--version"])
        assert_that(handled).is_true()
        assert_that(capsys.readouterr().out.strip()).is_equal_to(f"seekbar {seekbar.app.__version__}")

    def test_short_flag_handled(self, capsys):
        assert_that(_handle_version_flag(["-V"])).is_true()
        assert_that(capsys.readouterr().out).contains(seekbar.app.__version__)

    def test_no_flag_returns_false(self, capsys):
        assert_that(_handle_version_flag(["query", "text"])).is_false()
        assert_that(capsys.readouterr().out).is_empty()


class TestSingleInstanceGuard:
    _KEY = "seekbar-test-single-instance"

    def _cleanup(self, guard: _SingleInstanceGuard) -> None:
        if guard._server is not None:
            guard._server.close()
        QLocalServer.removeServer(self._KEY)

    @pytest.mark.usefixtures("qtbot")
    def test_first_instance_is_primary(self):
        guard = _SingleInstanceGuard(self._KEY)
        try:
            assert_that(guard.is_primary()).is_true()
        finally:
            self._cleanup(guard)

    def test_second_instance_signals_primary(self, qtbot: QtBot):
        primary = _SingleInstanceGuard(self._KEY)
        assert_that(primary.is_primary()).is_true()
        secondary = _SingleInstanceGuard(self._KEY)
        try:
            with qtbot.waitSignal(primary.activated, timeout=2000):
                assert_that(secondary.is_primary()).is_false()
        finally:
            self._cleanup(primary)
