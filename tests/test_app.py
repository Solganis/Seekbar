import ctypes
import ctypes.wintypes
import platform
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from assertpy2 import assert_that
from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QStyleOptionViewItem, QSystemTrayIcon

import seekbar.app

# noinspection PyProtectedMember
from seekbar.app import MainWindow, _FONT_FAMILY, _IS_DIR_ROLE, SETTINGS_APP, SETTINGS_ORG, _system_font_family
from seekbar.search import MAX_RESULTS
from seekbar.theme import DARK_THEME, LIGHT_THEME, ThemeMode

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

        paths = [window._result_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window._result_list.count())]
        assert_that(paths).is_equal_to(["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/xhostsy"])

    def test_secondary_sort_by_name_length(self, window: MainWindow):
        window._add_result("C:/dir/ab_hosts", 4)
        window._add_result("C:/dir/a_hosts", 4)

        names = [
            Path(window._result_list.item(i).data(Qt.ItemDataRole.UserRole)).name
            for i in range(window._result_list.count())
        ]
        assert_that(names).is_equal_to(["a_hosts", "ab_hosts"])

    def test_depth_sort_tiebreaker(self, window: MainWindow):
        window._add_result("C:/a/b/c/hosts", 0, depth=3)
        window._add_result("C:/hosts", 0, depth=1)

        paths = [window._result_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window._result_list.count())]
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


class TestSearchLifecycle:
    def test_clear_text_resets(self, window: MainWindow):
        window._search_input.setText("query")
        window._add_result("C:/test/file.txt", 4)
        window._search_input.setText("")
        assert_that(window._result_list.count()).is_equal_to(0)
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
        assert_that(window._result_list.count()).is_equal_to(0)

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
        assert_that(window._result_list.currentRow()).is_equal_to(0)

    def test_key_down_advances(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._result_list.setCurrentRow(0)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert_that(window._result_list.currentRow()).is_equal_to(1)

    def test_key_down_stays_at_bottom(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._result_list.setCurrentRow(1)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert_that(window._result_list.currentRow()).is_equal_to(1)

    def test_key_up_stays_at_top(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._result_list.setCurrentRow(0)
        qtbot.keyClick(window, Qt.Key.Key_Up)
        assert_that(window._result_list.currentRow()).is_equal_to(0)

    def test_move_selection_empty_list(self, window: MainWindow):
        window._move_selection(1)
        assert_that(window._result_list.currentRow()).is_equal_to(-1)

    def test_enter_opens_selected(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._add_result("C:/test/hosts", 0)
        window._result_list.setCurrentRow(0)
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._activate_selected()
        mock_desktop.openUrl.assert_called_once()

    def test_return_key_via_key_press_event(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._add_result("C:/test/hosts", 0)
        window._result_list.setCurrentRow(0)
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


class TestFileOpening:
    def test_open_file(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        window._add_result("C:/test/hosts", 0)
        item = window._result_list.item(0)
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_file(item)
        mock_desktop.openUrl.assert_called_once()

    def test_open_file_by_path(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        mock_desktop = MagicMock()
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_file_by_path("C:/test/hosts")
        mock_desktop.openUrl.assert_called_once()

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
        item = window._result_list.item(0)
        assert_that(item.data(_IS_DIR_ROLE)).is_false()

    def test_directory_stored(self, window: MainWindow):
        window._add_result("C:/test/folder", 4, is_dir=True)
        item = window._result_list.item(0)
        assert_that(item.data(_IS_DIR_ROLE)).is_true()


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
        assert_that(window._theme).is_same_as(LIGHT_THEME)

    def test_set_theme_updates_delegate(self, window: MainWindow):
        window._set_theme(LIGHT_THEME)
        assert_that(window._delegate._theme).is_same_as(LIGHT_THEME)

    def test_system_theme_change_in_auto_mode(self, window: MainWindow):
        window._theme_mode = ThemeMode.AUTO
        mock_app = MagicMock()
        mock_app.styleHints.return_value.colorScheme.return_value = Qt.ColorScheme.Light
        with patch("seekbar.theme.QGuiApplication.instance", return_value=mock_app):
            window._on_system_theme_changed(Qt.ColorScheme.Light)
        assert_that(window._theme).is_same_as(LIGHT_THEME)

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
        menu = window.findChild(seekbar.app.QMenu)
        if menu:
            actions = menu.actions()
            assert_that(actions).is_length(2)
            assert_that(actions[0].icon().isNull()).is_false()
            assert_that(actions[1].icon().isNull()).is_false()


class TestBatchInsertion:
    def test_batch_inserts_multiple_items(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/hosts", 0, 1, False),
                ("C:/dir/hosts.txt", 1, 1, False),
                ("C:/dir/xhostsy", 4, 1, False),
            ]
        )
        assert_that(window._result_list.count()).is_equal_to(3)

    def test_batch_sorted_correctly(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/xhostsy", 4, 1, False),
                ("C:/dir/hosts", 0, 1, False),
                ("C:/dir/hosts.txt", 1, 1, False),
            ]
        )
        paths = [window._result_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window._result_list.count())]
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
        assert_that(window._result_list.count()).is_equal_to(0)

    def test_batch_empty_list_noop(self, window: MainWindow):
        window._add_results_batch([])
        assert_that(window._result_list.count()).is_equal_to(0)
        assert_that(window._status_label.text()).is_empty()

    def test_batch_preserves_is_dir(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/folder", 4, 1, True),
                ("C:/dir/file.txt", 4, 1, False),
            ]
        )
        assert_that(window._result_list.item(0).data(_IS_DIR_ROLE)).is_true()
        assert_that(window._result_list.item(1).data(_IS_DIR_ROLE)).is_false()

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
        paths = [window._result_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window._result_list.count())]
        assert_that(paths).is_equal_to(["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/myhosts", "C:/dir/xhostsy"])


class TestExtendedNavigation:
    def test_page_down(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._result_list.setCurrentRow(0)
        qtbot.keyClick(window, Qt.Key.Key_PageDown)
        assert_that(window._result_list.currentRow()).is_equal_to(window._MAX_VISIBLE)

    def test_page_up(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._result_list.setCurrentRow(15)
        qtbot.keyClick(window, Qt.Key.Key_PageUp)
        assert_that(window._result_list.currentRow()).is_equal_to(15 - window._MAX_VISIBLE)

    def test_page_down_clamps_to_last(self, window: MainWindow, qtbot: QtBot):
        for i in range(5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._result_list.setCurrentRow(3)
        qtbot.keyClick(window, Qt.Key.Key_PageDown)
        assert_that(window._result_list.currentRow()).is_equal_to(4)

    def test_page_up_clamps_to_first(self, window: MainWindow, qtbot: QtBot):
        for i in range(5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._result_list.setCurrentRow(1)
        qtbot.keyClick(window, Qt.Key.Key_PageUp)
        assert_that(window._result_list.currentRow()).is_equal_to(0)


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


class TestDonatePopup:
    def test_f2_toggles_donate_popup(self, window: MainWindow, qtbot):
        assert_that(window._donate_popup.isHidden()).is_true()
        qtbot.keyClick(window, Qt.Key.Key_F2)
        assert_that(window._donate_popup.isHidden()).is_false()
        qtbot.keyClick(window, Qt.Key.Key_F2)
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


class TestSystemTray:
    def test_tray_exists(self, window: MainWindow):
        assert_that(window._tray).is_instance_of(QSystemTrayIcon)

    def test_tray_context_menu_actions(self, window: MainWindow):
        menu = window._tray.contextMenu()
        actions = menu.actions()
        assert_that(actions).is_length(2)
        assert_that(actions[0].text()).is_equal_to("Show / Hide")
        assert_that(actions[1].text()).is_equal_to("Quit")

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

    def test_hotkey_registers_on_init(self, qtbot: QtBot):
        with patch("seekbar.app._hotkey") as mock_hk:
            mock_hk.register_hotkey.return_value = True
            mock_hk.WM_HOTKEY = 0x0312
            main_window = MainWindow()
        qtbot.addWidget(main_window)
        assert_that(main_window._hotkey_registered).is_true()
        assert_that(main_window._hotkey_filter).is_not_none()
        main_window._tray.hide()

    def test_no_filter_on_registration_failure(self, window: MainWindow):
        assert_that(window._hotkey_filter).is_none()

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

    def test_filter_ignores_other_messages(self):
        callback = MagicMock()
        # noinspection PyProtectedMember
        hotkey_filter = seekbar.app._HotkeyFilter(callback)
        msg = ctypes.wintypes.MSG()
        msg.message = 0x0001
        result = hotkey_filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
        assert_that(result).is_equal_to((False, 0))
        callback.assert_not_called()

    def test_filter_ignores_non_windows_events(self):
        callback = MagicMock()
        # noinspection PyProtectedMember
        hotkey_filter = seekbar.app._HotkeyFilter(callback)
        result = hotkey_filter.nativeEventFilter(b"xcb_generic_event_t", 0)
        assert_that(result).is_equal_to((False, 0))
        callback.assert_not_called()

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
