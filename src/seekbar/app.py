from __future__ import annotations

import bisect
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
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

if TYPE_CHECKING:
    from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QStyleOptionViewItem

_SURFACE = "#1E1E1E"
_SURFACE_VARIANT = "#2C2C2C"
_ON_SURFACE = "#E0E0E0"
_ON_SURFACE_VARIANT = "#808080"
_PRIMARY = "#BB86FC"
_OUTLINE = "#333333"
_HOVER = "#252525"
_SELECTED = "#332D41"


class _ResultDelegate(QStyledItemDelegate):
    _ITEM_HEIGHT = 52

    @override
    def paint(  # pragma: no cover
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        path_str = index.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(_SELECTED))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(_HOVER))

        left = option.rect.left() + 16
        width = option.rect.width() - 32

        name_font = QFont("Segoe UI", 10)
        name_font.setWeight(QFont.Weight.Medium)
        painter.setFont(name_font)
        painter.setPen(QColor(_ON_SURFACE))
        name_rect = QRect(left, option.rect.top() + 6, width, 22)
        elided = QFontMetrics(name_font).elidedText(p.name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        path_font = QFont("Segoe UI", 8)
        painter.setFont(path_font)
        painter.setPen(QColor(_ON_SURFACE_VARIANT))
        path_rect = QRect(left, option.rect.top() + 28, width, 18)
        elided = QFontMetrics(path_font).elidedText(str(p.parent), Qt.TextElideMode.ElideMiddle, width)
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

        self._worker: SearchWorker | None = None
        self._drag_pos: QPoint | None = None
        self._sort_keys: list[tuple[int, int]] = []

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
        self._sync_height()

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() // 4)

    def _build_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("card")
        return card

    def _build_search_input(self) -> QLineEdit:
        inp = QLineEdit()
        inp.setObjectName("searchInput")
        inp.setPlaceholderText("Search files...")
        inp.setFixedHeight(self._SEARCH_HEIGHT)
        inp.textChanged.connect(self._on_text_changed)
        inp.returnPressed.connect(self._start_search_immediate)
        palette = inp.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(_ON_SURFACE_VARIANT))
        inp.setPalette(palette)
        return inp

    def _build_status_label(self) -> QLabel:
        lbl = QLabel()
        lbl.setObjectName("statusLabel")
        return lbl

    def _build_close_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("closeButton")
        btn.setFixedSize(self._SEARCH_HEIGHT - 12, self._SEARCH_HEIGHT - 12)
        btn.setIcon(self._make_close_icon())
        btn.setIconSize(QSize(14, 14))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.close)
        return btn

    @staticmethod
    def _make_close_icon() -> QIcon:
        size = 14
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(_ON_SURFACE_VARIANT), 1.5))
        m = 3
        painter.drawLine(m, m, size - m, size - m)
        painter.drawLine(size - m, m, m, size - m)
        painter.end()
        return QIcon(pixmap)

    def _build_separator(self) -> QFrame:
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(1)
        sep.hide()
        return sep

    def _build_result_list(self) -> QListWidget:
        lst = QListWidget()
        lst.setObjectName("resultList")
        lst.setItemDelegate(_ResultDelegate(lst))
        lst.setMouseTracking(True)
        lst.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        lst.customContextMenuRequested.connect(self._show_context_menu)
        lst.itemDoubleClicked.connect(self._open_file)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.hide()
        return lst

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
        self.setStyleSheet(f"""
            #card {{
                background-color: {_SURFACE};
                border: 1px solid {_OUTLINE};
                border-radius: {self._RADIUS}px;
            }}
            #searchInput {{
                background-color: transparent;
                border: none;
                color: {_ON_SURFACE};
                font-size: 15px;
                font-family: "Segoe UI", sans-serif;
                padding: 0 16px;
                selection-background-color: {_PRIMARY};
            }}
            #separator {{
                background-color: {_OUTLINE};
                border: none;
            }}
            #statusLabel {{
                color: {_ON_SURFACE_VARIANT};
                font-size: 11px;
                font-family: "Segoe UI", sans-serif;
                padding: 0;
                background-color: transparent;
            }}
            #closeButton {{
                background-color: transparent;
                border: none;
                border-radius: {(self._SEARCH_HEIGHT - 12) // 2}px;
            }}
            #closeButton:hover {{
                background-color: {_HOVER};
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
                background: {_OUTLINE};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QMenu {{
                background-color: {_SURFACE_VARIANT};
                color: {_ON_SURFACE};
                border: 1px solid {_OUTLINE};
                border-radius: 8px;
                padding: 4px;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {_HOVER};
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
            card_h = self._SEARCH_HEIGHT + 1 + visible * self._ITEM_HEIGHT + self._RADIUS
        else:
            card_h = self._SEARCH_HEIGHT

        self.setFixedHeight(card_h + self._MARGIN * 2)

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
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    # -- search lifecycle --

    def _on_text_changed(self, text: str) -> None:
        if not text.strip():
            self._stop_search()
            self._result_list.clear()
            self._sort_keys.clear()
            self._status_label.clear()
            self._sync_height()
            return
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

        self._worker = SearchWorker(query)
        self._worker.found.connect(self._add_result)
        self._worker.finished.connect(self._on_search_done)
        self._worker.start()

    def _stop_search(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        self._worker = None

    def _add_result(self, path: str, score: int) -> None:
        key = (score, len(Path(path).name))
        pos = bisect.bisect_right(self._sort_keys, key)
        self._sort_keys.insert(pos, key)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
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
                subprocess.Popen(["explorer", "/select,", path])
            case "Darwin":
                subprocess.Popen(["open", "-R", path])
            case _:
                parent = str(Path(path).parent)
                QDesktopServices.openUrl(QUrl.fromLocalFile(parent))


def main() -> None:  # pragma: no cover
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
