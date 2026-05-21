import platform
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QModelIndex, QPoint, QSettings, Qt
from PySide6.QtWidgets import QStyleOptionViewItem

import seekbar.app

# noinspection PyProtectedMember
from seekbar.app import _FONT_FAMILY, _IS_DIR_ROLE, SETTINGS_APP, SETTINGS_ORG, _system_font_family
from seekbar.search import MAX_RESULTS
from seekbar.theme import DARK_THEME, LIGHT_THEME, ThemeMode

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from seekbar.app import MainWindow


class TestMainWindow:
    def test_window_title(self, window: MainWindow):
        assert window.windowTitle() == "Seekbar"

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
        expected = window._search_height + window._MARGIN * 2
        assert window.height() == expected

    def test_delegate_size_hint(self, window: MainWindow):
        delegate = window._delegate
        size = delegate.sizeHint(QStyleOptionViewItem(), QModelIndex())
        assert size.height() == delegate.item_height

    def test_delegate_item_height_from_metrics(self, window: MainWindow):
        delegate = window._delegate
        expected = delegate._name_metrics.height() + delegate._path_metrics.height() + delegate._VERTICAL_PADDING
        assert delegate.item_height == expected

    def test_delegate_has_cached_fonts(self, window: MainWindow):
        delegate = window._result_list.itemDelegate()
        assert hasattr(delegate, "_name_font")
        assert hasattr(delegate, "_path_font")
        assert hasattr(delegate, "_name_metrics")
        assert hasattr(delegate, "_path_metrics")


class TestFontFamily:
    def test_font_family_not_empty(self):
        assert _FONT_FAMILY
        assert isinstance(_FONT_FAMILY, str)

    def test_windows_font(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        assert _system_font_family() == "Segoe UI"

    def test_darwin_font(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        assert _system_font_family() == ".AppleSystemUIFont"

    def test_linux_font(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        assert _system_font_family() == "Sans"


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

    def test_depth_sort_tiebreaker(self, window: MainWindow):
        window._add_result("C:/a/b/c/hosts", 0, depth=3)
        window._add_result("C:/hosts", 0, depth=1)

        paths = [window._result_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window._result_list.count())]
        assert paths == ["C:/hosts", "C:/a/b/c/hosts"]

    def test_results_become_visible(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        assert not window._result_list.isHidden()
        assert not window._separator.isHidden()


class TestHeightSync:
    def test_grows_with_single_result(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        item_h = window._delegate.item_height
        expected = window._search_height + 1 + item_h + window._RADIUS + window._MARGIN * 2
        assert window.height() == expected

    def test_capped_at_max_visible(self, window: MainWindow):
        for i in range(window._MAX_VISIBLE + 5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        item_h = window._delegate.item_height
        expected = window._search_height + 1 + window._MAX_VISIBLE * item_h + window._RADIUS + window._MARGIN * 2
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

    def test_add_result_ignored_without_worker(self, window: MainWindow):
        window._worker = None
        window._add_result("C:/test/stale.txt", 4)
        assert window._result_list.count() == 0

    def test_done_ignored_without_worker(self, window: MainWindow):
        window._worker = None
        window._status_label.setText("searching.")
        window._on_search_done(0)
        assert window._status_label.text() == "searching."

    def test_clear_text_stops_debounce_timer(self, window: MainWindow):
        window._search_input.setText("query")
        assert window._debounce_timer.isActive()
        window._search_input.setText("")
        assert not window._debounce_timer.isActive()

    def test_typing_shows_searching_immediately(self, window: MainWindow):
        window._on_search_done(0)
        assert window._status_label.text() == "no results"
        window._search_input.setText("newquery")
        assert window._status_label.text() == "searching."

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
        assert window._status_label.text() == "searching."
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
        assert not window._searching_timer.isActive()
        mock_worker = MagicMock()
        monkeypatch.setattr(seekbar.app, "SearchWorker", lambda _q: mock_worker)
        window._start_search()
        assert window._searching_timer.isActive()

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


class TestKeyboardNavigation:
    def test_escape_clears_text_first(self, window: MainWindow, qtbot: QtBot):
        window.show()
        window._search_input.setText("query")
        qtbot.keyClick(window, Qt.Key.Key_Escape)
        assert window._search_input.text() == ""
        assert window.isVisible()

    def test_escape_closes_when_empty(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.keyClick(window, Qt.Key.Key_Escape)
        assert not window.isVisible()

    def test_close_button(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.mouseClick(window._close_button, Qt.MouseButton.LeftButton)
        assert not window.isVisible()

    def test_tab_does_not_change_focus(self, window: MainWindow):
        assert window.focusNextPrevChild(True) is True

    def test_backtab_does_not_change_focus(self, window: MainWindow):
        assert window.focusNextPrevChild(False) is True

    def test_non_escape_key(self, window: MainWindow, qtbot: QtBot):
        window.show()
        qtbot.keyClick(window, Qt.Key.Key_A)
        assert window.isVisible()

    def test_key_down_selects_first(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert window._result_list.currentRow() == 0

    def test_key_down_advances(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._result_list.setCurrentRow(0)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert window._result_list.currentRow() == 1

    def test_key_down_stays_at_bottom(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._result_list.setCurrentRow(1)
        qtbot.keyClick(window, Qt.Key.Key_Down)
        assert window._result_list.currentRow() == 1

    def test_key_up_stays_at_top(self, window: MainWindow, qtbot: QtBot):
        window._add_result("C:/test/a.txt", 4)
        window._result_list.setCurrentRow(0)
        qtbot.keyClick(window, Qt.Key.Key_Up)
        assert window._result_list.currentRow() == 0

    def test_move_selection_empty_list(self, window: MainWindow):
        window._move_selection(1)
        assert window._result_list.currentRow() == -1

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
        assert window._theme_mode != initial_mode


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
        assert item.data(_IS_DIR_ROLE) is False

    def test_directory_stored(self, window: MainWindow):
        window._add_result("C:/test/folder", 4, is_dir=True)
        item = window._result_list.item(0)
        assert item.data(_IS_DIR_ROLE) is True


class TestResultDelegate:
    def test_has_folder_icon(self, window: MainWindow):
        delegate = window._delegate
        assert delegate.folder_icon is not None
        assert not delegate.folder_icon.isNull()

    def test_has_file_icon(self, window: MainWindow):
        delegate = window._delegate
        assert delegate.file_icon is not None
        assert not delegate.file_icon.isNull()

    def test_icon_size(self, window: MainWindow):
        delegate = window._delegate
        assert delegate.folder_icon.width() == 20
        assert delegate.folder_icon.height() == 20
        assert delegate.file_icon.width() == 20
        assert delegate.file_icon.height() == 20

    def test_set_theme_rebuilds_icons(self, window: MainWindow):
        delegate = window._delegate
        old_folder = delegate.folder_icon
        old_file = delegate.file_icon
        delegate.set_theme(LIGHT_THEME)
        assert delegate._theme is LIGHT_THEME
        assert delegate.folder_icon is not old_folder
        assert delegate.file_icon is not old_file
        assert not delegate.folder_icon.isNull()
        assert not delegate.file_icon.isNull()


class TestThemeSwitching:
    def test_default_mode_is_auto(self, window: MainWindow):
        assert window._theme_mode == ThemeMode.AUTO

    def test_cycle_auto_to_light(self, window: MainWindow):
        window._cycle_theme()
        assert window._theme_mode == ThemeMode.LIGHT

    def test_cycle_light_to_dark(self, window: MainWindow):
        window._theme_mode = ThemeMode.LIGHT
        window._cycle_theme()
        assert window._theme_mode == ThemeMode.DARK

    def test_cycle_dark_to_auto(self, window: MainWindow):
        window._theme_mode = ThemeMode.DARK
        window._cycle_theme()
        assert window._theme_mode == ThemeMode.AUTO

    def test_cycle_applies_theme(self, window: MainWindow):
        window._cycle_theme()
        assert window._theme is LIGHT_THEME

    def test_set_theme_updates_delegate(self, window: MainWindow):
        window._set_theme(LIGHT_THEME)
        assert window._delegate._theme is LIGHT_THEME

    def test_system_theme_change_in_auto_mode(self, window: MainWindow):
        window._theme_mode = ThemeMode.AUTO
        mock_app = MagicMock()
        mock_app.styleHints.return_value.colorScheme.return_value = Qt.ColorScheme.Light
        with patch("seekbar.theme.QGuiApplication.instance", return_value=mock_app):
            window._on_system_theme_changed(Qt.ColorScheme.Light)
        assert window._theme is LIGHT_THEME

    def test_system_theme_change_ignored_in_manual_mode(self, window: MainWindow):
        window._theme_mode = ThemeMode.DARK
        window._set_theme(DARK_THEME)
        window._on_system_theme_changed(Qt.ColorScheme.Light)
        assert window._theme is DARK_THEME

    def test_close_icon_updates_on_theme_switch(self, window: MainWindow):
        old_icon = window._close_button.icon()
        window._set_theme(LIGHT_THEME)
        new_icon = window._close_button.icon()
        assert old_icon.cacheKey() != new_icon.cacheKey()


class TestThemePersistence:
    def test_cycle_saves_to_settings(self, window: MainWindow):
        window._cycle_theme()
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        assert settings.value("theme_mode") == ThemeMode.LIGHT.value

    def test_load_saved_mode(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("theme_mode", "dark")
        loaded = window._load_theme_mode()
        assert loaded == ThemeMode.DARK

    def test_load_invalid_mode_defaults_to_auto(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("theme_mode", "garbage")
        loaded = window._load_theme_mode()
        assert loaded == ThemeMode.AUTO

    def test_load_missing_key_defaults_to_auto(self, window: MainWindow):
        loaded = window._load_theme_mode()
        assert loaded == ThemeMode.AUTO


class TestResultLimitIndicator:
    def test_format_count_below_limit(self, window: MainWindow):
        assert window._format_count(50) == "50 results"

    def test_format_count_at_limit(self, window: MainWindow):
        assert window._format_count(MAX_RESULTS) == f"{MAX_RESULTS}+ results"

    def test_format_count_above_limit(self, window: MainWindow):
        assert window._format_count(MAX_RESULTS + 1) == f"{MAX_RESULTS}+ results"

    def test_status_shows_limit_on_done(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(seekbar.app, "MAX_RESULTS", 3)
        for i in range(3):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._on_search_done(3)
        assert "3+" in window._status_label.text()


class TestWindowPositionPersistence:
    def test_saves_position_on_close(self, window: MainWindow):
        window.show()
        window.move(QPoint(100, 200))
        window.close()
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        assert settings.value("window_x") == 100
        assert settings.value("window_y") == 200

    def test_restores_saved_position(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        screen = window.screen().geometry()
        pos_x = screen.x() + 50
        pos_y = screen.y() + 50
        settings.setValue("window_x", pos_x)
        settings.setValue("window_y", pos_y)
        loaded = window._load_window_position()
        assert loaded == QPoint(pos_x, pos_y)

    def test_window_uses_saved_position_on_init(self, qtbot: QtBot):
        screen = seekbar.app.QApplication.primaryScreen().geometry()
        pos_x = screen.x() + 75
        pos_y = screen.y() + 75
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("window_x", pos_x)
        settings.setValue("window_y", pos_y)
        fresh_window = seekbar.app.MainWindow()
        qtbot.addWidget(fresh_window)
        assert fresh_window.pos() == QPoint(pos_x, pos_y)

    def test_fallback_on_offscreen_position(self, window: MainWindow):
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("window_x", -99999)
        settings.setValue("window_y", -99999)
        loaded = window._load_window_position()
        assert loaded is None

    def test_fallback_on_missing_position(self, window: MainWindow):
        loaded = window._load_window_position()
        assert loaded is None


class TestPlaceholder:
    def test_placeholder_text(self, window: MainWindow):
        assert window._search_input.placeholderText() == "Search all drives..."


class TestContextMenuIcons:
    def test_actions_have_icons(self, window: MainWindow):
        window._add_result("C:/test/hosts", 0)
        window.show()
        with patch.object(seekbar.app.QMenu, "popup"):
            window._show_context_menu(QPoint(10, 10))
        menu = window.findChild(seekbar.app.QMenu)
        if menu:
            actions = menu.actions()
            assert len(actions) == 2
            assert not actions[0].icon().isNull()
            assert not actions[1].icon().isNull()


class TestBatchInsertion:
    def test_batch_inserts_multiple_items(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/hosts", 0, 1, False),
                ("C:/dir/hosts.txt", 1, 1, False),
                ("C:/dir/xhostsy", 4, 1, False),
            ]
        )
        assert window._result_list.count() == 3

    def test_batch_sorted_correctly(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/xhostsy", 4, 1, False),
                ("C:/dir/hosts", 0, 1, False),
                ("C:/dir/hosts.txt", 1, 1, False),
            ]
        )
        paths = [window._result_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window._result_list.count())]
        assert paths == ["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/xhostsy"]

    def test_batch_updates_status_once(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/a.txt", 4, 1, False),
                ("C:/dir/b.txt", 4, 1, False),
                ("C:/dir/c.txt", 4, 1, False),
            ]
        )
        assert "3" in window._status_label.text()

    def test_batch_syncs_height(self, window: MainWindow):
        window._add_results_batch([("C:/dir/a.txt", 4, 1, False)])
        item_h = window._delegate.item_height
        expected = window._search_height + 1 + item_h + window._RADIUS + window._MARGIN * 2
        assert window.height() == expected

    def test_batch_ignored_without_worker(self, window: MainWindow):
        window._worker = None
        window._add_results_batch([("C:/dir/a.txt", 4, 1, False)])
        assert window._result_list.count() == 0

    def test_batch_empty_list_noop(self, window: MainWindow):
        window._add_results_batch([])
        assert window._result_list.count() == 0
        assert window._status_label.text() == ""

    def test_batch_preserves_is_dir(self, window: MainWindow):
        window._add_results_batch(
            [
                ("C:/dir/folder", 4, 1, True),
                ("C:/dir/file.txt", 4, 1, False),
            ]
        )
        assert window._result_list.item(0).data(_IS_DIR_ROLE) is True
        assert window._result_list.item(1).data(_IS_DIR_ROLE) is False

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
        assert paths == ["C:/dir/hosts", "C:/dir/hosts.txt", "C:/dir/myhosts", "C:/dir/xhostsy"]


class TestExtendedNavigation:
    def test_page_down(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._result_list.setCurrentRow(0)
        qtbot.keyClick(window, Qt.Key.Key_PageDown)
        assert window._result_list.currentRow() == window._MAX_VISIBLE

    def test_page_up(self, window: MainWindow, qtbot: QtBot):
        for i in range(20):
            window._add_result(f"C:/test/file_{i:02d}.txt", 4)
        window._result_list.setCurrentRow(15)
        qtbot.keyClick(window, Qt.Key.Key_PageUp)
        assert window._result_list.currentRow() == 15 - window._MAX_VISIBLE

    def test_page_down_clamps_to_last(self, window: MainWindow, qtbot: QtBot):
        for i in range(5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._result_list.setCurrentRow(3)
        qtbot.keyClick(window, Qt.Key.Key_PageDown)
        assert window._result_list.currentRow() == 4

    def test_page_up_clamps_to_first(self, window: MainWindow, qtbot: QtBot):
        for i in range(5):
            window._add_result(f"C:/test/file_{i}.txt", 4)
        window._result_list.setCurrentRow(1)
        qtbot.keyClick(window, Qt.Key.Key_PageUp)
        assert window._result_list.currentRow() == 0


class TestSearchingAnimation:
    def test_start_sets_initial_text(self, window: MainWindow):
        window._start_searching_animation()
        assert window._status_label.text() == "searching."
        assert window._searching_timer.isActive()

    def test_stop_stops_timer(self, window: MainWindow):
        window._start_searching_animation()
        window._stop_searching_animation()
        assert not window._searching_timer.isActive()

    def test_cycle_one_to_two(self, window: MainWindow):
        window._status_label.setText("searching.")
        window._animate_searching()
        assert window._status_label.text() == "searching.."

    def test_cycle_two_to_three(self, window: MainWindow):
        window._status_label.setText("searching..")
        window._animate_searching()
        assert window._status_label.text() == "searching..."

    def test_cycle_three_to_one(self, window: MainWindow):
        window._status_label.setText("searching...")
        window._animate_searching()
        assert window._status_label.text() == "searching."

    def test_clear_text_stops_animation(self, window: MainWindow):
        window._search_input.setText("query")
        assert window._searching_timer.isActive()
        window._search_input.setText("")
        assert not window._searching_timer.isActive()

    def test_batch_stops_animation(self, window: MainWindow):
        window._start_searching_animation()
        assert window._searching_timer.isActive()
        window._add_results_batch([("C:/dir/a.txt", 4, 1, False)])
        assert not window._searching_timer.isActive()

    def test_search_done_stops_animation(self, window: MainWindow):
        window._start_searching_animation()
        assert window._searching_timer.isActive()
        window._on_search_done(0)
        assert not window._searching_timer.isActive()


class TestErrorFeedback:
    def test_open_file_failure(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        mock_desktop = MagicMock()
        mock_desktop.openUrl.return_value = False
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_file_by_path("C:/nonexistent/file.txt")
        assert window._status_label.text() == "Failed to open file"

    def test_open_folder_oserror(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(seekbar.app.subprocess, "run", MagicMock(side_effect=OSError))
        window._open_folder("C:/test/hosts")
        assert window._status_label.text() == "Failed to open folder"

    def test_open_folder_linux_failure(self, window: MainWindow, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        mock_desktop = MagicMock()
        mock_desktop.openUrl.return_value = False
        monkeypatch.setattr(seekbar.app, "QDesktopServices", mock_desktop)
        window._open_folder("/home/test/file.txt")
        assert window._status_label.text() == "Failed to open folder"


class TestTempStatus:
    def test_shows_message(self, window: MainWindow):
        window._show_temp_status("Error occurred")
        assert window._status_label.text() == "Error occurred"

    def test_restore_with_results(self, window: MainWindow):
        window._add_result("C:/test/a.txt", 4)
        window._add_result("C:/test/b.txt", 4)
        window._show_temp_status("Error")
        window._restore_status()
        assert "2" in window._status_label.text()

    def test_restore_without_results(self, window: MainWindow):
        window._show_temp_status("Error")
        window._restore_status()
        assert window._status_label.text() == ""


class TestHelpPopup:
    def test_initially_hidden(self, window: MainWindow):
        assert window._help_popup.isHidden()

    def test_toggle_shows(self, window: MainWindow):
        window._toggle_help()
        assert not window._help_popup.isHidden()

    def test_toggle_twice_hides(self, window: MainWindow):
        window._toggle_help()
        window._toggle_help()
        assert window._help_popup.isHidden()

    def test_f1_key_toggles(self, window: MainWindow, qtbot: QtBot):
        qtbot.keyClick(window, Qt.Key.Key_F1)
        assert not window._help_popup.isHidden()

    def test_text_change_hides_help(self, window: MainWindow):
        window._toggle_help()
        assert not window._help_popup.isHidden()
        window._search_input.setText("query")
        assert window._help_popup.isHidden()

    def test_hide_help_when_visible(self, window: MainWindow):
        window._toggle_help()
        window._hide_help()
        assert window._help_popup.isHidden()

    def test_hide_help_when_already_hidden(self, window: MainWindow):
        window._hide_help()
        assert window._help_popup.isHidden()

    def test_help_content(self, window: MainWindow):
        html = window._help_popup.text()
        assert "Esc" in html
        assert "F1" in html
        assert "<table" in html

    def test_help_updates_on_theme_switch(self, window: MainWindow):
        old_html = window._help_popup.text()
        window._set_theme(LIGHT_THEME)
        new_html = window._help_popup.text()
        assert old_html != new_html

    def test_sync_height_with_help(self, window: MainWindow):
        window._toggle_help()
        help_height = window._help_popup.sizeHint().height()
        expected = window._search_height + 1 + help_height + window._RADIUS + window._MARGIN * 2
        assert window._height_target == expected
        window._finalize_height()
        assert window.height() == expected

    def test_help_hides_results_list(self, window: MainWindow):
        window._add_result("C:/test/file.txt", 4)
        window._toggle_help()
        assert window._result_list.isHidden()
        assert not window._separator.isHidden()

    def test_help_shows_separator_without_results(self, window: MainWindow):
        window._toggle_help()
        assert not window._separator.isHidden()
        assert window._result_list.isHidden()

    def test_batch_skips_sync_when_help_open(self, window: MainWindow):
        window._toggle_help()
        window._finalize_height()
        height_before = window.height()
        window._add_result("C:/test/file.txt", 4)
        assert window.height() == height_before

    def test_done_skips_sync_when_help_open(self, window: MainWindow):
        window._toggle_help()
        window._finalize_height()
        height_before = window.height()
        window._on_search_done(0)
        assert window.height() == height_before
