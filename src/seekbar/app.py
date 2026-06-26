import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QByteArray,
    QEasingCurve,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QSize,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListView,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from seekbar import __version__, autostart, content, icons, settings, styles
from seekbar.constants import _FONT_FAMILY, _IS_DIR_ROLE
from seekbar.delegate import _ResultDelegate
from seekbar.model import _RecencyStore, _ResultModel
from seekbar.search import MAX_RESULTS, SearchWorker
from seekbar.single_instance import _SINGLE_INSTANCE_KEY, _SingleInstanceGuard
from seekbar.theme import ACCENTS, Theme, ThemeMode, TrayIconMode, is_dark, resolve_theme

if sys.platform == "win32":  # pragma: no cover - Windows-only, not reachable off win32
    import ctypes.wintypes

    from seekbar import hotkey as _hotkey

    # _HotkeyFilter reads ctypes.wintypes.MSG, a Windows-only type unresolved off Windows
    # noinspection PyUnresolvedReferences
    class _HotkeyFilter(QAbstractNativeEventFilter):
        def __init__(self, callback: Callable[[], object]) -> None:
            super().__init__()
            self._callback = callback

        @override
        def nativeEventFilter(self, event_type: QByteArray | bytes | bytearray | memoryview, message: int) -> object:
            if event_type == b"windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == _hotkey.WM_HOTKEY:
                    self._callback()
                    return True, 0
            return False, 0

    _hotkey_mac = None
elif sys.platform == "darwin":  # pragma: no cover - macOS-only branch
    from seekbar import _hotkey_macos as _hotkey_mac

    _hotkey = None
else:  # pragma: no cover - non-Windows/macOS fallback
    _hotkey = None
    _hotkey_mac = None

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QCloseEvent, QKeyEvent, QMouseEvent


class MainWindow(QWidget):
    _MAX_VISIBLE = 9
    _MARGIN = 2
    _RADIUS = 12

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Seekbar")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(620)

        self._theme_mode = settings.load_theme_mode()
        self._accent_id = settings.load_accent()
        self._tray_icon_mode = settings.load_tray_icon_mode()
        self._theme = resolve_theme(self._theme_mode, self._accent_id)
        self.setWindowIcon(icons.make_app_icon(icons.icon_color(self._tray_icon_mode, self._theme)))

        search_font = QFont(_FONT_FAMILY, 11)
        self._search_height = QFontMetrics(search_font).height() * 2 + 10

        self._worker: SearchWorker | None = None
        self._drag_pos: QPoint | None = None
        self._recency = _RecencyStore()

        self._init_timers()

        self._card = self._build_card()
        self._search_input = self._build_search_input()
        self._status_label = self._build_status_label()
        self._close_button = self._build_close_button()
        self._separator = self._build_separator()
        self._result_list = self._build_result_list()
        self._help_popup = self._build_help_popup()
        self._donate_popup = self._build_donate_popup()
        self._settings_popup = self._build_settings_popup()
        self._popups = (self._help_popup, self._donate_popup, self._settings_popup)
        self._assemble_layout()
        self._apply_styles()
        self._update_palette()
        self._sync_height()

        cast("QApplication", QApplication.instance()).styleHints().colorSchemeChanged.connect(
            self._on_system_theme_changed,
        )

        self._tray = self._build_tray()
        self._init_hotkey()

        saved_pos = settings.load_window_position()
        if saved_pos:
            self.move(saved_pos)
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - self.width()) // 2, screen.height() // 4)

    def _init_timers(self) -> None:
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._start_search)

        self._searching_timer = QTimer(self)
        self._searching_timer.setInterval(400)
        self._searching_timer.timeout.connect(self._animate_searching)

        self._temp_status_timer = QTimer(self)
        self._temp_status_timer.setSingleShot(True)
        self._temp_status_timer.timeout.connect(self._restore_status)

        self._height_target = 0
        self._content_height = 0
        self._height_anim = QVariantAnimation(self)
        self._height_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._height_anim.setDuration(150)
        self._height_anim.valueChanged.connect(self._apply_animated_height)
        self._height_anim.finished.connect(self._finalize_height)

    def _set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_styles()
        self._update_palette()
        icon = icons.make_app_icon(icons.icon_color(self._tray_icon_mode, self._theme))
        self.setWindowIcon(icon)
        self._tray.setIcon(icon)
        self._close_button.setIcon(icons.make_close_icon(theme))
        self._help_popup.setText(content.help_html(self._theme))
        self._donate_popup.setText(content.donate_html(self._theme))
        self._refresh_settings()
        self._delegate.set_theme(theme)
        self._result_list.viewport().update()

    def _cycle_theme(self) -> None:
        match self._theme_mode:
            case ThemeMode.AUTO:
                self._theme_mode = ThemeMode.LIGHT
            case ThemeMode.LIGHT:
                self._theme_mode = ThemeMode.DARK
            case ThemeMode.DARK:  # pragma: no branch - exhaustive over ThemeMode, no-match arm unreachable
                self._theme_mode = ThemeMode.AUTO
        settings.save_theme_mode(self._theme_mode)
        self._set_theme(resolve_theme(self._theme_mode, self._accent_id))

    def _on_system_theme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._theme_mode == ThemeMode.AUTO:
            self._set_theme(resolve_theme(ThemeMode.AUTO, self._accent_id))

    def _set_accent(self, accent_id: str) -> None:
        if accent_id == self._accent_id:
            return
        self._accent_id = accent_id
        settings.save_accent(accent_id)
        self._set_theme(resolve_theme(self._theme_mode, accent_id))

    def _set_tray_icon_mode(self, mode: TrayIconMode) -> None:
        if mode == self._tray_icon_mode:
            return
        self._tray_icon_mode = mode
        settings.save_tray_icon_mode(mode)
        icon = icons.make_app_icon(icons.icon_color(self._tray_icon_mode, self._theme))
        self.setWindowIcon(icon)
        self._tray.setIcon(icon)
        self._refresh_settings()

    def _build_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("card")
        return card

    def _build_search_input(self) -> QLineEdit:
        search_field = QLineEdit()
        search_field.setObjectName("searchInput")
        search_field.setAccessibleName("Search input")
        search_field.setPlaceholderText("Search all drives...")
        search_field.setFixedHeight(self._search_height)
        search_field.textChanged.connect(self._on_text_changed)
        search_field.returnPressed.connect(self._activate_selected)
        search_field.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        search_field.customContextMenuRequested.connect(self._show_input_context_menu)
        search_field.installEventFilter(self)
        return search_field

    def _update_palette(self) -> None:
        palette = self._search_input.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(self._theme.on_surface_variant))
        self._search_input.setPalette(palette)

    # instance method by design - groups with the other _build_* widget builders
    # noinspection PyMethodMayBeStatic
    def _build_status_label(self) -> QLabel:
        label = QLabel()
        label.setObjectName("statusLabel")
        return label

    def _build_close_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("closeButton")
        button.setAccessibleName("Close")
        button.setToolTip("")
        button.setFixedSize(self._search_height - 12, self._search_height - 12)
        button.setIcon(icons.make_close_icon(self._theme))
        button.setIconSize(QSize(14, 14))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.close)
        return button

    # instance method by design - groups with the other _build_* widget builders
    # noinspection PyMethodMayBeStatic
    def _build_separator(self) -> QFrame:
        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        separator.hide()
        return separator

    def _build_result_list(self) -> QListView:
        self._result_model = _ResultModel(self._recency, self)
        result_list = QListView()
        result_list.setObjectName("resultList")
        result_list.setAccessibleName("Search results")
        result_list.setModel(self._result_model)
        result_list.setUniformItemSizes(True)
        self._delegate = _ResultDelegate(self._theme, result_list)
        result_list.setItemDelegate(self._delegate)
        result_list.setMouseTracking(True)
        result_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        result_list.customContextMenuRequested.connect(self._show_context_menu)
        result_list.doubleClicked.connect(self._open_index)
        result_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        result_list.hide()
        return result_list

    def _build_help_popup(self) -> QLabel:
        label = QLabel()
        label.setObjectName("helpPopup")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(content.help_html(self._theme))
        label.hide()
        return label

    def _build_donate_popup(self) -> QLabel:
        label = QLabel()
        label.setObjectName("donatePopup")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self._on_donate_link)
        label.setText(content.donate_html(self._theme))
        label.hide()
        return label

    def _on_donate_link(self, url: str) -> None:
        self._drag_pos = None
        if url.startswith("copy:"):
            address = url.removeprefix("copy:")
            QApplication.clipboard().setText(address)
            self._show_temp_status("Copied!", 2000)
        else:
            self._hide_popups()
            QDesktopServices.openUrl(QUrl(url))

    def _build_settings_popup(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settingsPopup")
        outer = QHBoxLayout(panel)
        outer.setContentsMargins(16, 12, 16, 12)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("Accent"), 0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(QLabel("Tray icon"), 1, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        accent_row = QHBoxLayout()
        accent_row.setSpacing(8)
        self._accent_group = QButtonGroup(panel)
        self._accent_buttons: dict[str, QPushButton] = {}
        for accent_id in ACCENTS:
            button = QPushButton()
            button.setCheckable(True)
            button.setFixedSize(40, 24)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda *_args, chosen=accent_id: self._set_accent(chosen))
            self._accent_group.addButton(button)
            accent_row.addWidget(button)
            self._accent_buttons[accent_id] = button
        grid.addLayout(accent_row, 0, 1)

        tray_row = QHBoxLayout()
        tray_row.setSpacing(8)
        self._tray_group = QButtonGroup(panel)
        self._tray_buttons: dict[TrayIconMode, QPushButton] = {}
        for mode in TrayIconMode:
            button = QPushButton(mode.value.capitalize())
            button.setObjectName("trayButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda *_args, chosen=mode: self._set_tray_icon_mode(chosen))
            self._tray_group.addButton(button)
            tray_row.addWidget(button)
            self._tray_buttons[mode] = button
        grid.addLayout(tray_row, 1, 1)

        outer.addStretch()
        outer.addLayout(grid)
        outer.addStretch()

        self._refresh_settings()
        panel.hide()
        return panel

    def _refresh_settings(self) -> None:
        dark = is_dark(self._theme)
        for accent_id, button in self._accent_buttons.items():
            accent = ACCENTS[accent_id]
            primary_color = accent.primary_dark if dark else accent.primary_light
            selected_color = accent.selected_dark if dark else accent.selected_light
            button.setStyleSheet(styles.accent_swatch_qss(self._theme, selected_color, primary_color))
            button.setChecked(accent_id == self._accent_id)
        for mode, button in self._tray_buttons.items():
            button.setChecked(mode == self._tray_icon_mode)

    def _assemble_layout(self) -> None:
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 6, 0)
        top_row.setSpacing(4)
        top_row.addWidget(self._search_input, stretch=1)
        top_row.addWidget(self._status_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self._close_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._card_layout = QVBoxLayout(self._card)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(0)
        self._card_layout.addLayout(top_row)
        self._card_layout.addWidget(self._separator)
        self._card_layout.addWidget(self._result_list)
        self._card_layout.addWidget(self._help_popup)
        self._card_layout.addWidget(self._donate_popup)
        self._card_layout.addWidget(self._settings_popup)
        # Keeps content top-pinned and the card's own background (not the desktop) in the slack mid-shrink.
        self._card_layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._MARGIN, self._MARGIN, self._MARGIN, self._MARGIN)
        # Let our explicit setFixedHeight drive the height animation; the layout must not impose a
        # minimum window height from the card and fight it (that makes the window jump).
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        outer.addWidget(self._card, alignment=Qt.AlignmentFlag.AlignTop)

    def _apply_styles(self) -> None:
        theme = self._theme
        menu = styles.menu_qss(theme)
        if hasattr(self, "_tray"):
            tray_menu = self._tray.contextMenu()
            if tray_menu is not None:
                tray_menu.setStyleSheet(menu)
        self.setStyleSheet(styles.window_qss(theme, self._RADIUS, self._search_height, menu))

    def _sync_height(self, *, animate: bool = False) -> None:
        self._height_anim.stop()
        count = self._result_model.rowCount()
        has_results = count > 0
        visible_popup = next((popup for popup in self._popups if not popup.isHidden()), None)
        popup_visible = visible_popup is not None

        self._result_list.setVisible(has_results and not popup_visible)
        self._separator.setVisible(has_results or popup_visible)
        has_content = has_results or popup_visible
        self._card_layout.setContentsMargins(0, 0, 0, self._RADIUS if has_content else 0)

        if visible_popup is not None:
            popup_height = visible_popup.sizeHint().height()
            card_height = self._search_height + 1 + popup_height + self._RADIUS
        elif has_results:
            visible = min(count, self._MAX_VISIBLE)
            self._result_list.setFixedHeight(visible * self._delegate.item_height)
            card_height = self._search_height + 1 + visible * self._delegate.item_height + self._RADIUS
        else:
            card_height = self._search_height

        self._content_height = card_height
        target = card_height + self._MARGIN * 2
        self._fit_card(self.height())
        if animate and target != self.height():
            self._height_target = target
            self._height_anim.setStartValue(self.height())
            self._height_anim.setEndValue(target)
            self._height_anim.start()
        else:
            self._set_height_preserving_pos(target)

    def _fit_card(self, window_height: int) -> None:
        # Card fills the window (its background covers a shrink) but never shrinks below its content
        # (a mid-grow window clips it instead of squeezing the popup up into the search bar).
        self._card.setFixedHeight(max(self._content_height, window_height - self._MARGIN * 2))

    def _set_height_preserving_pos(self, height: int) -> None:
        pos = self.pos()
        self._fit_card(height)
        self.setFixedHeight(height)
        if self.pos() != pos:
            self.move(pos)

    def _apply_animated_height(self, value: int) -> None:
        self._set_height_preserving_pos(int(value))

    def _finalize_height(self) -> None:
        self._set_height_preserving_pos(self._height_target)

    # -- window dragging --

    def _start_drag(self, event: QMouseEvent) -> None:
        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_drag(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    @override
    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag_pos = None

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._search_input:
            event_type = event.type()
            if event_type == QEvent.Type.MouseButtonPress:
                mouse_event = cast("QMouseEvent", event)
                if (
                    mouse_event.button() == Qt.MouseButton.LeftButton
                    and mouse_event.modifiers() & Qt.KeyboardModifier.AltModifier
                ):
                    self._start_drag(mouse_event)
                    return True
            elif event_type == QEvent.Type.KeyPress:
                key_event = cast("QKeyEvent", event)
                # A focused QLineEdit consumes Home/End for its text cursor, so they never reach
                # keyPressEvent. Reroute them to result navigation (like Up/Down/PageUp/PageDown) while
                # results are listed; with none, they fall through to the line edit's text cursor.
                if key_event.key() in (Qt.Key.Key_Home, Qt.Key.Key_End) and self._result_model.rowCount() > 0:
                    self._handle_navigation(key_event.key())
                    return True
            elif self._drag_pos is not None:
                if event_type == QEvent.Type.MouseMove:
                    mouse_event = cast("QMouseEvent", event)
                    # Drag only while the button is held, so a stale offset can't fling the window on hover.
                    if mouse_event.buttons() & Qt.MouseButton.LeftButton:
                        self.move(mouse_event.globalPosition().toPoint() - self._drag_pos)
                        return True
                elif event_type == QEvent.Type.MouseButtonRelease:
                    self._drag_pos = None
                    return True
        return super().eventFilter(watched, event)

    @override
    def focusNextPrevChild(self, _next: bool) -> bool:
        return True

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        match event.key():
            case Qt.Key.Key_Escape:
                if self._search_input.text():
                    self._search_input.clear()
                else:
                    self.close()
            case (
                Qt.Key.Key_Down
                | Qt.Key.Key_Up
                | Qt.Key.Key_PageDown
                | Qt.Key.Key_PageUp
                | Qt.Key.Key_Home
                | Qt.Key.Key_End
            ):
                self._handle_navigation(event.key())
            case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                self._activate_selected()
            case Qt.Key.Key_T if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._cycle_theme()
            case Qt.Key.Key_Q if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._quit_app()
            case Qt.Key.Key_F1:
                self._toggle_help()
            case Qt.Key.Key_F2:
                self._toggle_settings()
            case Qt.Key.Key_F3:
                self._toggle_donate()
            case _:
                super().keyPressEvent(event)

    def _handle_navigation(self, key: int) -> None:
        match key:
            case Qt.Key.Key_Down:
                self._move_selection(1)
            case Qt.Key.Key_Up:
                self._move_selection(-1)
            case Qt.Key.Key_PageDown:
                self._move_selection(self._MAX_VISIBLE)
            case Qt.Key.Key_PageUp:
                self._move_selection(-self._MAX_VISIBLE)
            case Qt.Key.Key_Home:
                self._move_selection(-self._result_model.rowCount())
            case Qt.Key.Key_End:  # pragma: no branch - reached only with the six nav keys, no-match arm unreachable
                self._move_selection(self._result_model.rowCount())

    def _move_selection(self, delta: int) -> None:
        count = self._result_model.rowCount()
        if count == 0:
            return
        new_row = max(0, min(count - 1, self._current_row() + delta))
        self._select_row(new_row)

    def _current_row(self) -> int:
        return self._result_list.currentIndex().row()

    def _select_row(self, row: int) -> None:
        self._result_list.setCurrentIndex(self._result_model.index(row))

    def _activate_selected(self) -> None:
        row = self._current_row()
        if row < 0:
            self._start_search_immediate()
        else:
            self._open_file_by_path(self._result_model.path_at(row))

    # -- search lifecycle --

    def _on_text_changed(self, text: str) -> None:
        popup_dismissed = self._any_popup_visible()
        self._hide_all_popups()
        if not text.strip():
            self._debounce_timer.stop()
            self._stop_search()
            self._stop_searching_animation()
            self._result_model.clear()
            self._status_label.clear()
            self._sync_height(animate=popup_dismissed)
            return
        self._stop_search()
        self._start_searching_animation()
        self._debounce_timer.start()
        if popup_dismissed:
            self._result_model.clear()
            self._sync_height(animate=True)

    def _start_search_immediate(self) -> None:
        self._debounce_timer.stop()
        self._start_search()

    def _start_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            return
        self._stop_search()
        self._result_model.clear()
        if not self._searching_timer.isActive():
            self._start_searching_animation()
        self._sync_height()

        worker = SearchWorker(query)
        worker.batch_found.connect(self._add_results_batch)
        worker.finished.connect(self._on_search_done)
        worker.start()
        self._worker = worker

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        if self._tray.isVisible():
            settings.save_window_position(self.pos())
            event.ignore()
            self.hide()
        else:
            settings.save_window_position(self.pos())
            self._stop_search()
            super().closeEvent(event)

    def _stop_search(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        self._worker = None

    def _add_results_batch(self, results: list[tuple[str, int, int, bool]]) -> None:
        if self._worker is None or not results:
            return
        self._stop_searching_animation()
        self._result_model.add_batch(results)
        self._status_label.setText(self._format_count(self._result_model.rowCount()))
        if not self._any_popup_visible():
            self._sync_height()

    def _add_result(
        self,
        path: str,
        score: int,
        depth: int = 0,
        is_dir: bool = False,  # noqa: FBT001, FBT002 - test convenience wrapper with bool params
    ) -> None:
        self._add_results_batch([(path, score, depth, is_dir)])

    @staticmethod
    def _format_count(count: int) -> str:
        if count >= MAX_RESULTS:
            return f"{MAX_RESULTS}+ results"
        return f"{count} results"

    def _on_search_done(self, _total: int) -> None:
        if self._worker is None:
            return
        self._stop_searching_animation()
        count = self._result_model.rowCount()
        self._status_label.setText("no results" if count == 0 else self._format_count(count))
        if not self._any_popup_visible():
            self._sync_height()

    # -- searching animation --

    def _start_searching_animation(self) -> None:
        self._status_label.setText("searching.")
        self._searching_timer.start()

    def _stop_searching_animation(self) -> None:
        self._searching_timer.stop()

    def _animate_searching(self) -> None:
        text = self._status_label.text()
        match text:
            case "searching.":
                self._status_label.setText("searching..")
            case "searching..":
                self._status_label.setText("searching...")
            case _:
                self._status_label.setText("searching.")

    # -- actions --

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self._result_list.indexAt(pos)
        if not index.isValid():
            return
        path = self._result_model.path_at(index.row())
        is_dir = index.data(_IS_DIR_ROLE)
        menu = QMenu(self)
        file_icon = QIcon(self._delegate.file_icon)
        folder_icon = QIcon(self._delegate.folder_icon)
        act_open = QAction(folder_icon if is_dir else file_icon, "Open folder" if is_dir else "Open file", self)
        act_open.triggered.connect(lambda: self._open_file_by_path(path))
        act_folder = QAction(folder_icon, "Open containing folder", self)
        act_folder.triggered.connect(lambda: self._open_folder(path))
        menu.addAction(act_open)
        menu.addAction(act_folder)
        menu.popup(self._result_list.mapToGlobal(pos))

    def _show_input_context_menu(self, pos: QPoint) -> None:
        menu = self._search_input.createStandardContextMenu()
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.setStyleSheet(styles.menu_qss(self._theme))
        on_surface = self._theme.on_surface
        for action in menu.actions():
            icon = action.icon()
            if not icon.isNull():
                action.setIcon(icons.tint_icon(icon, on_surface))
        menu.popup(self._search_input.mapToGlobal(pos))

    def _open_index(self, index: QModelIndex) -> None:
        self._open_file_by_path(self._result_model.path_at(index.row()))

    def _open_file_by_path(self, path: str) -> None:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self._recency.record(path)
        else:
            self._show_temp_status("Failed to open file")

    def _open_folder(self, path: str) -> None:
        try:
            match platform.system():
                case "Windows":
                    subprocess.run(["explorer", "/select,", path], check=False)
                case "Darwin":
                    subprocess.run(["open", "-R", path], check=False)
                case _:
                    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))):
                        self._show_temp_status("Failed to open folder")
        except OSError:
            self._show_temp_status("Failed to open folder")

    # -- feedback --

    def _show_temp_status(self, message: str, duration_ms: int = 3000) -> None:
        self._status_label.setText(message)
        self._temp_status_timer.setInterval(duration_ms)
        self._temp_status_timer.start()

    def _restore_status(self) -> None:
        count = self._result_model.rowCount()
        if count > 0:
            self._status_label.setText(self._format_count(count))
        else:
            self._status_label.setText("")

    # -- popups --

    def _toggle_help(self) -> None:
        was_hidden = self._help_popup.isHidden()
        self._donate_popup.hide()
        self._settings_popup.hide()
        self._help_popup.setVisible(was_hidden)
        self._sync_height(animate=was_hidden)

    def _toggle_donate(self) -> None:
        was_hidden = self._donate_popup.isHidden()
        self._help_popup.hide()
        self._settings_popup.hide()
        self._donate_popup.setVisible(was_hidden)
        self._sync_height(animate=was_hidden)

    def _toggle_settings(self) -> None:
        was_hidden = self._settings_popup.isHidden()
        self._help_popup.hide()
        self._donate_popup.hide()
        self._settings_popup.setVisible(was_hidden)
        self._sync_height(animate=was_hidden)

    def _any_popup_visible(self) -> bool:
        return any(not popup.isHidden() for popup in self._popups)

    def _hide_all_popups(self) -> None:
        for popup in self._popups:
            popup.hide()

    def _hide_popups(self) -> None:
        if self._any_popup_visible():
            self._hide_all_popups()
            self._sync_height()

    # -- system tray --

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(icons.make_app_icon(icons.icon_color(self._tray_icon_mode, self._theme)), self)
        tray.setToolTip("Seekbar")
        # parent the menu to the window so it inherits the cascaded QMenu stylesheet;
        # a parentless top-level QMenu is not reliably styled by the native Windows 11 menu backend
        menu = QMenu(self)
        menu.setStyleSheet(styles.menu_qss(self._theme))
        act_toggle = QAction("Show / Hide", self)
        act_toggle.triggered.connect(self._toggle_visibility)
        self._autostart_action = QAction("Launch at startup", self)
        self._autostart_action.setCheckable(True)
        self._autostart_action.setChecked(autostart.is_enabled())
        # connect after setChecked so the initial state does not emit a spurious toggle
        self._autostart_action.toggled.connect(self._on_autostart_toggled)
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_toggle)
        menu.addAction(self._autostart_action)
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        return tray

    @staticmethod
    def _on_autostart_toggled(enabled: bool) -> None:  # noqa: FBT001 - Qt toggled(bool) signal slot
        autostart.set_enabled(enabled)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def _toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self._show_window()

    def _show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":  # pragma: no cover - Windows-only, not reachable off win32
            # windll.user32.SetForegroundWindow is a dynamic WinDLL attribute, Windows-only
            # noinspection PyUnresolvedReferences
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _quit_app(self) -> None:
        settings.save_window_position(self.pos())
        self._stop_search()
        if _hotkey is not None and self._hotkey_registered:  # pragma: no cover - Windows-only, not reachable off win32
            _hotkey.unregister_hotkey()
            app = QApplication.instance()
            if app is not None and self._hotkey_filter is not None:
                app.removeNativeEventFilter(self._hotkey_filter)
        elif _hotkey_mac is not None and self._hotkey_registered:
            _hotkey_mac.unregister_hotkey()
        self._tray.hide()
        QApplication.quit()

    # -- global hotkey --

    def _init_hotkey(self) -> None:
        self._hotkey_registered = False
        self._hotkey_filter: QAbstractNativeEventFilter | None = None
        if _hotkey is not None:  # pragma: no cover - Windows-only, not reachable off win32
            self._hotkey_registered = _hotkey.register_hotkey()
            if not self._hotkey_registered:
                return
            self._hotkey_filter = _HotkeyFilter(self._toggle_visibility)
            app = QApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self._hotkey_filter)
        elif _hotkey_mac is not None:
            self._hotkey_registered = _hotkey_mac.register_hotkey(self._toggle_visibility)


def _handle_version_flag(argv: list[str]) -> bool:
    if "--version" in argv or "-V" in argv:
        sys.stdout.write(f"seekbar {__version__}\n")
        return True
    return False


def main() -> None:  # pragma: no cover - entry point starts Qt event loop, not unit-testable
    if _handle_version_flag(sys.argv[1:]):
        return
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    guard = _SingleInstanceGuard(_SINGLE_INSTANCE_KEY)
    if not guard.is_primary():
        return
    window = MainWindow()
    guard.setParent(window)
    # main() wires the second-instance ping to the window's show method
    guard.activated.connect(window._show_window)  # noqa: SLF001
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
