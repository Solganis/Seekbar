from __future__ import annotations

import bisect
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PySide6.QtCore import QRect, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from seekbar.search import SearchWorker
from seekbar.theme import Theme, ThemeMode, resolve_theme

if TYPE_CHECKING:
    from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint
    from PySide6.QtGui import QCloseEvent, QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QStyleOptionViewItem

_IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1
_ICON_SIZE = 20
_SETTINGS_ORG = "Seekbar"
_SETTINGS_APP = "Seekbar"


def _system_font_family() -> str:
    match platform.system():
        case "Windows":
            return "Segoe UI"
        case "Darwin":
            return ".AppleSystemUIFont"
        case _:
            return "Sans"


_FONT_FAMILY = _system_font_family()


class _ResultDelegate(QStyledItemDelegate):
    _ITEM_HEIGHT = 52

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._name_font = QFont(_FONT_FAMILY, 10)
        self._name_font.setWeight(QFont.Weight.Medium)
        self._name_metrics = QFontMetrics(self._name_font)
        self._path_font = QFont(_FONT_FAMILY, 8)
        self._path_metrics = QFontMetrics(self._path_font)
        self._folder_icon = self._make_folder_icon()
        self._file_icon = self._make_file_icon()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._folder_icon = self._make_folder_icon()
        self._file_icon = self._make_file_icon()

    def _make_folder_icon(self) -> QPixmap:
        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.moveTo(1, 8)
        path.lineTo(1, 4)
        path.lineTo(7, 4)
        path.lineTo(9, 6)
        path.lineTo(19, 6)
        path.lineTo(19, 17)
        path.lineTo(1, 17)
        path.closeSubpath()
        painter.fillPath(path, QColor(self._theme.folder_color))
        painter.end()
        return pixmap

    def _make_file_icon(self) -> QPixmap:
        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QPainterPath()
        body.moveTo(3, 1)
        body.lineTo(13, 1)
        body.lineTo(17, 5)
        body.lineTo(17, 19)
        body.lineTo(3, 19)
        body.closeSubpath()
        painter.fillPath(body, QColor(self._theme.file_color))
        fold = QPainterPath()
        fold.moveTo(13, 1)
        fold.lineTo(13, 5)
        fold.lineTo(17, 5)
        fold.closeSubpath()
        painter.fillPath(fold, QColor(self._theme.file_fold_color))
        painter.end()
        return pixmap

    @override
    def paint(  # pragma: no cover - Qt paint events cannot be triggered reliably in headless tests
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        path_str = index.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        file_path = Path(path_str)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(self._theme.selected))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(self._theme.hover))

        is_dir = index.data(_IS_DIR_ROLE)
        icon = self._folder_icon if is_dir else self._file_icon
        icon_x = option.rect.left() + 12
        icon_y = option.rect.top() + (self._ITEM_HEIGHT - _ICON_SIZE) // 2
        painter.drawPixmap(icon_x, icon_y, icon)

        left = option.rect.left() + 40
        width = option.rect.width() - 52

        painter.setFont(self._name_font)
        painter.setPen(QColor(self._theme.on_surface))
        name_rect = QRect(left, option.rect.top() + 6, width, 22)
        elided = self._name_metrics.elidedText(file_path.name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        painter.setFont(self._path_font)
        painter.setPen(QColor(self._theme.on_surface_variant))
        path_rect = QRect(left, option.rect.top() + 28, width, 18)
        elided = self._path_metrics.elidedText(str(file_path.parent), Qt.TextElideMode.ElideMiddle, width)
        painter.drawText(path_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        painter.restore()

    @override
    def sizeHint(self, _option: QStyleOptionViewItem, _index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(0, self._ITEM_HEIGHT)


class MainWindow(QWidget):
    _ITEM_HEIGHT = 52
    _MAX_VISIBLE = 9
    _SEARCH_HEIGHT = 46
    _MARGIN = 2
    _RADIUS = 12

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Seekbar")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(620)

        self._theme_mode = self._load_theme_mode()
        self._theme = resolve_theme(self._theme_mode)
        self.setWindowIcon(self._make_app_icon(self._theme))

        self._worker: SearchWorker | None = None
        self._drag_pos: QPoint | None = None
        self._sort_keys: list[tuple[int, int, int]] = []

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._start_search)

        self._card = self._build_card()
        self._search_input = self._build_search_input()
        self._status_label = self._build_status_label()
        self._close_button = self._build_close_button()
        self._separator = self._build_separator()
        self._result_list = self._build_result_list()
        self._assemble_layout()
        self._apply_styles()
        self._update_palette()
        self._sync_height()

        cast("QApplication", QApplication.instance()).styleHints().colorSchemeChanged.connect(
            self._on_system_theme_changed,
        )

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() // 4)

    @staticmethod
    def _load_theme_mode() -> ThemeMode:
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        raw = settings.value("theme_mode", ThemeMode.AUTO.value)
        try:
            return ThemeMode(raw)
        except ValueError:
            return ThemeMode.AUTO

    @staticmethod
    def _save_theme_mode(mode: ThemeMode) -> None:
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue("theme_mode", mode.value)

    def _set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_styles()
        self._update_palette()
        self.setWindowIcon(self._make_app_icon(theme))
        self._close_button.setIcon(self._make_close_icon(theme))
        self._delegate.set_theme(theme)
        self._result_list.viewport().update()

    def _cycle_theme(self) -> None:
        match self._theme_mode:
            case ThemeMode.AUTO:
                self._theme_mode = ThemeMode.LIGHT
            case ThemeMode.LIGHT:
                self._theme_mode = ThemeMode.DARK
            case ThemeMode.DARK:
                self._theme_mode = ThemeMode.AUTO
        self._save_theme_mode(self._theme_mode)
        self._set_theme(resolve_theme(self._theme_mode))

    def _on_system_theme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._theme_mode == ThemeMode.AUTO:
            self._set_theme(resolve_theme(ThemeMode.AUTO))

    def _build_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("card")
        return card

    def _build_search_input(self) -> QLineEdit:
        search_field = QLineEdit()
        search_field.setObjectName("searchInput")
        search_field.setPlaceholderText("Search files...")
        search_field.setFixedHeight(self._SEARCH_HEIGHT)
        search_field.textChanged.connect(self._on_text_changed)
        search_field.returnPressed.connect(self._activate_selected)
        return search_field

    def _update_palette(self) -> None:
        palette = self._search_input.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(self._theme.on_surface_variant))
        self._search_input.setPalette(palette)

    # noinspection PyMethodMayBeStatic
    def _build_status_label(self) -> QLabel:
        label = QLabel()
        label.setObjectName("statusLabel")
        return label

    def _build_close_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("closeButton")
        button.setFixedSize(self._SEARCH_HEIGHT - 12, self._SEARCH_HEIGHT - 12)
        button.setIcon(self._make_close_icon(self._theme))
        button.setIconSize(QSize(14, 14))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.close)
        return button

    @staticmethod
    def _make_app_icon(theme: Theme) -> QIcon:
        icon = QIcon()
        for size in (16, 32, 48):
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            scale = size / 32.0
            color = QColor(theme.primary)
            painter.setPen(QPen(color, 2.0 * scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            cx, cy, radius = 12.0 * scale, 12.0 * scale, 8.0 * scale
            painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))
            painter.setPen(QPen(color, 2.5 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            hx, hy = cx + radius * 0.707, cy + radius * 0.707
            painter.drawLine(int(hx), int(hy), int(hx + 7 * scale), int(hy + 7 * scale))
            painter.end()
            icon.addPixmap(pixmap)
        return icon

    @staticmethod
    def _make_close_icon(theme: Theme) -> QIcon:
        size = 14
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(theme.on_surface_variant), 1.5))
        margin = 3
        painter.drawLine(margin, margin, size - margin, size - margin)
        painter.drawLine(size - margin, margin, margin, size - margin)
        painter.end()
        return QIcon(pixmap)

    # noinspection PyMethodMayBeStatic
    def _build_separator(self) -> QFrame:
        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        separator.hide()
        return separator

    def _build_result_list(self) -> QListWidget:
        result_list = QListWidget()
        result_list.setObjectName("resultList")
        self._delegate = _ResultDelegate(self._theme, result_list)
        result_list.setItemDelegate(self._delegate)
        result_list.setMouseTracking(True)
        result_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        result_list.customContextMenuRequested.connect(self._show_context_menu)
        result_list.itemDoubleClicked.connect(self._open_file)
        result_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        result_list.hide()
        return result_list

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._MARGIN, self._MARGIN, self._MARGIN, self._MARGIN)
        outer.addWidget(self._card)

    def _apply_styles(self) -> None:
        theme = self._theme
        self.setStyleSheet(f"""
            #card {{
                background-color: {theme.surface};
                border: 1px solid {theme.outline};
                border-radius: {self._RADIUS}px;
            }}
            #searchInput {{
                background-color: transparent;
                border: none;
                color: {theme.on_surface};
                font-size: 15px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                padding: 0 16px;
                selection-background-color: {theme.primary};
                selection-color: {theme.surface};
            }}
            #separator {{
                background-color: {theme.outline};
                border: none;
            }}
            #statusLabel {{
                color: {theme.on_surface_variant};
                font-size: 11px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                padding: 0;
                background-color: transparent;
            }}
            #closeButton {{
                background-color: transparent;
                border: none;
                border-radius: {(self._SEARCH_HEIGHT - 12) // 2}px;
            }}
            #closeButton:hover {{
                background-color: {theme.hover};
            }}
            #resultList {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            #resultList::item {{
                border: none;
                padding: 0;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.outline};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QMenu {{
                background-color: {theme.surface_variant};
                color: {theme.on_surface};
                border: 1px solid {theme.outline};
                border-radius: 8px;
                padding: 4px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {theme.hover};
            }}
        """)

    def _sync_height(self) -> None:
        count = self._result_list.count()
        has_results = count > 0

        self._result_list.setVisible(has_results)
        self._separator.setVisible(has_results)
        self._card_layout.setContentsMargins(0, 0, 0, self._RADIUS if has_results else 0)

        if has_results:
            visible = min(count, self._MAX_VISIBLE)
            self._result_list.setFixedHeight(visible * self._ITEM_HEIGHT)
            card_height = self._SEARCH_HEIGHT + 1 + visible * self._ITEM_HEIGHT + self._RADIUS
        else:
            card_height = self._SEARCH_HEIGHT

        self.setFixedHeight(card_height + self._MARGIN * 2)

    # -- window dragging --

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    @override
    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag_pos = None

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        match event.key():
            case Qt.Key.Key_Escape:
                self.close()
            case Qt.Key.Key_Down:
                self._move_selection(1)
            case Qt.Key.Key_Up:
                self._move_selection(-1)
            case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                self._activate_selected()
            case Qt.Key.Key_T if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._cycle_theme()
            case _:
                super().keyPressEvent(event)

    def _move_selection(self, delta: int) -> None:
        count = self._result_list.count()
        if count == 0:
            return
        current = self._result_list.currentRow()
        new_row = max(0, min(count - 1, current + delta))
        self._result_list.setCurrentRow(new_row)

    def _activate_selected(self) -> None:
        item = self._result_list.currentItem()
        if item:
            self._open_file(item)
        else:
            self._start_search_immediate()

    # -- search lifecycle --

    def _on_text_changed(self, text: str) -> None:
        if not text.strip():
            self._stop_search()
            self._result_list.clear()
            self._sort_keys.clear()
            self._status_label.clear()
            self._sync_height()
            return
        self._stop_search()
        self._status_label.setText("searching...")
        self._debounce_timer.start()

    def _start_search_immediate(self) -> None:
        self._debounce_timer.stop()
        self._start_search()

    def _start_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            return
        self._stop_search()
        self._result_list.clear()
        self._sort_keys.clear()
        self._status_label.setText("searching...")
        self._sync_height()

        worker = SearchWorker(query)
        worker.found.connect(self._add_result)
        worker.finished.connect(self._on_search_done)
        worker.start()
        self._worker = worker

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_search()
        super().closeEvent(event)

    def _stop_search(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        self._worker = None

    def _add_result(
        self, path: str, score: int, depth: int = 0, is_dir: bool = False,  # noqa: FBT001, FBT002 - Qt signal emits positional args
    ) -> None:
        key = (score, depth, len(Path(path).name))
        pos = bisect.bisect_right(self._sort_keys, key)
        self._sort_keys.insert(pos, key)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setData(_IS_DIR_ROLE, is_dir)
        item.setSizeHint(QSize(0, self._ITEM_HEIGHT))
        self._result_list.insertItem(pos, item)
        count = self._result_list.count()
        self._status_label.setText(f"{count} results")
        if count <= self._MAX_VISIBLE:
            self._sync_height()

    def _on_search_done(self, _total: int) -> None:
        count = self._result_list.count()
        self._status_label.setText("no results" if count == 0 else f"{count} results")
        self._sync_height()

    # -- actions --

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self._result_list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        act_open = QAction("Open file", self)
        act_open.triggered.connect(lambda: self._open_file_by_path(path))
        act_folder = QAction("Open containing folder", self)
        act_folder.triggered.connect(lambda: self._open_folder(path))
        menu.addAction(act_open)
        menu.addAction(act_folder)
        menu.popup(self._result_list.mapToGlobal(pos))

    def _open_file(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        self._open_file_by_path(path)

    @staticmethod
    def _open_file_by_path(path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @staticmethod
    def _open_folder(path: str) -> None:
        match platform.system():
            case "Windows":
                subprocess.run(["explorer", "/select,", path], check=False)
            case "Darwin":
                subprocess.run(["open", "-R", path], check=False)
            case _:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))


def main() -> None:  # pragma: no cover - entry point starts Qt event loop, not unit-testable
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
