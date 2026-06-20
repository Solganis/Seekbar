import bisect
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PySide6.QtCore import (
    QAbstractListModel,
    QAbstractNativeEventFilter,
    QByteArray,
    QEasingCurve,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSettings,
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
    QListView,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from seekbar.search import MAX_RESULTS, SearchWorker
from seekbar.theme import Theme, ThemeMode, resolve_theme

if sys.platform == "win32":
    import ctypes.wintypes

    from seekbar import hotkey as _hotkey

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

else:  # pragma: no cover - non-Windows fallback
    _hotkey = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtCore import QPersistentModelIndex
    from PySide6.QtGui import QCloseEvent, QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QStyleOptionViewItem

_IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1
_HELP_SHORTCUTS: tuple[tuple[tuple[str, ...], str] | None, ...] = (
    (("↑", "↓"), "Navigate"),
    (("PgUp", "PgDn"), "Jump page"),
    (("Enter",), "Open selected"),
    (("Esc",), "Clear / Hide"),
    None,
    (("Ctrl+Alt+S",), "Show / Hide"),
    (("Ctrl+Q",), "Quit"),
    (("Ctrl+T",), "Toggle theme"),
    (("Alt+Drag",), "Move window"),
    None,
    (("F1",), "This help"),
    (("F2",), "About"),
)

_DONATE_WEB: tuple[tuple[str, str], ...] = (
    ("GitHub", "https://github.com/Solganis/Seekbar"),
    ("DonationAlerts", "https://www.donationalerts.com/r/Solganis"),
    ("Boosty", "https://boosty.to/solganis"),
)

_DONATE_CRYPTO: tuple[tuple[str, str], ...] = (
    ("TON", "UQAZDskr7UZE9Hn8Q8asCfmYIsicgL0KS9YNvRJ5NF53OPPo"),
    ("USDT (TRC-20)", "TG32fyLCxPcTCmtFXayDkvAvAF9goci9st"),
)
_ICON_SIZE = 20
SETTINGS_ORG = "Seekbar"
SETTINGS_APP = "Seekbar"


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
    _VERTICAL_PADDING = 22

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._name_font = QFont(_FONT_FAMILY, 10)
        self._name_font.setWeight(QFont.Weight.Medium)
        self._name_metrics = QFontMetrics(self._name_font)
        self._path_font = QFont(_FONT_FAMILY, 8)
        self._path_metrics = QFontMetrics(self._path_font)
        self._item_height = self._name_metrics.height() + self._path_metrics.height() + self._VERTICAL_PADDING
        self._folder_icon = self._make_folder_icon()
        self._file_icon = self._make_file_icon()

    @property
    def item_height(self) -> int:
        return self._item_height

    @property
    def folder_icon(self) -> QPixmap:
        return self._folder_icon

    @property
    def file_icon(self) -> QPixmap:
        return self._file_icon

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
        icon_y = option.rect.top() + (self._item_height - _ICON_SIZE) // 2
        painter.drawPixmap(icon_x, icon_y, icon)

        left = option.rect.left() + 40
        width = option.rect.width() - 52
        name_h = self._name_metrics.height()
        path_h = self._path_metrics.height()
        pad = (self._item_height - name_h - path_h) // 3

        painter.setFont(self._name_font)
        painter.setPen(QColor(self._theme.on_surface))
        name_rect = QRect(left, option.rect.top() + pad, width, name_h + pad)
        elided = self._name_metrics.elidedText(file_path.name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        painter.setFont(self._path_font)
        painter.setPen(QColor(self._theme.on_surface_variant))
        path_rect = QRect(left, option.rect.top() + pad + name_h + pad, width, path_h + pad)
        parent_name = file_path.parent.name or str(file_path.parent)
        elided = self._path_metrics.elidedText(parent_name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(path_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        painter.restore()

    @override
    def sizeHint(self, _option: QStyleOptionViewItem, _index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(0, self._item_height)


_NO_PARENT = QModelIndex()


class _RecencyStore:
    """Persists recently opened paths (most-recent-first) so repeat results rank higher."""

    _LIMIT = 500
    _KEY = "recent_paths"

    def __init__(self) -> None:
        self._paths = self._load()
        self._ranks = {path: index for index, path in enumerate(self._paths)}

    @classmethod
    def _load(cls) -> list[str]:
        raw = QSettings(SETTINGS_ORG, SETTINGS_APP).value(cls._KEY, "[]")
        if not isinstance(raw, str):
            return []
        try:
            stored = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(stored, list):
            return []
        return [path for path in stored if isinstance(path, str)]

    def rank(self, path: str) -> int:
        return self._ranks.get(path, self._LIMIT)

    def record(self, path: str) -> None:
        if self._paths[:1] == [path]:
            return
        if path in self._ranks:
            self._paths.remove(path)
        self._paths.insert(0, path)
        del self._paths[self._LIMIT :]
        self._ranks = {stored: index for index, stored in enumerate(self._paths)}
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(self._KEY, json.dumps(self._paths))


def _basename_length(path: str) -> int:
    # Length of the final path component without allocating a Path; handles either separator.
    return len(path) - max(path.rfind("\\"), path.rfind("/")) - 1


class _ResultModel(QAbstractListModel):
    def __init__(self, recency: _RecencyStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._recency = recency
        self._keys: list[tuple[int, int, int, int]] = []
        self._rows: list[tuple[str, bool]] = []

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _NO_PARENT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.UserRole:
            return self._rows[index.row()][0]
        if role == _IS_DIR_ROLE:
            return self._rows[index.row()][1]
        return None

    def add_batch(self, results: list[tuple[str, int, int, bool]]) -> None:
        for path, score, depth, is_dir in results:
            # Recency breaks ties within a score tier; basename length is the final tiebreaker.
            key = (score, self._recency.rank(path), depth, _basename_length(path))
            pos = bisect.bisect_right(self._keys, key)
            self.beginInsertRows(_NO_PARENT, pos, pos)
            self._keys.insert(pos, key)
            self._rows.insert(pos, (path, is_dir))
            self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._keys.clear()
        self._rows.clear()
        self.endResetModel()

    def path_at(self, row: int) -> str:
        return self._rows[row][0]


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

        self._theme_mode = self._load_theme_mode()
        self._theme = resolve_theme(self._theme_mode)
        self.setWindowIcon(self._make_app_icon(self._theme))

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
        self._assemble_layout()
        self._apply_styles()
        self._update_palette()
        self._sync_height()

        cast("QApplication", QApplication.instance()).styleHints().colorSchemeChanged.connect(
            self._on_system_theme_changed,
        )

        self._tray = self._build_tray()
        self._init_hotkey()

        saved_pos = self._load_window_position()
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

        self._help_hide_timer = QTimer(self)
        self._help_hide_timer.setSingleShot(True)
        self._help_hide_timer.setInterval(5000)
        self._help_hide_timer.timeout.connect(self._hide_popups)

        self._temp_status_timer = QTimer(self)
        self._temp_status_timer.setSingleShot(True)
        self._temp_status_timer.timeout.connect(self._restore_status)

        self._height_target = 0
        self._height_anim = QVariantAnimation(self)
        self._height_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._height_anim.setDuration(150)
        self._height_anim.valueChanged.connect(self._apply_animated_height)
        self._height_anim.finished.connect(self._finalize_height)

    @staticmethod
    def _load_theme_mode() -> ThemeMode:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        raw = settings.value("theme_mode", ThemeMode.AUTO.value)
        try:
            return ThemeMode(raw)
        except ValueError:
            return ThemeMode.AUTO

    @staticmethod
    def _save_theme_mode(mode: ThemeMode) -> None:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("theme_mode", mode.value)

    @staticmethod
    def _load_window_position() -> QPoint | None:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        pos_x = settings.value("window_x")
        pos_y = settings.value("window_y")
        if pos_x is None or pos_y is None:
            return None
        point = QPoint(int(pos_x), int(pos_y))
        for screen in QApplication.screens():
            if screen.geometry().contains(point):
                return point
        return None

    @staticmethod
    def _save_window_position(pos: QPoint) -> None:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("window_x", pos.x())
        settings.setValue("window_y", pos.y())

    def _set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_styles()
        self._update_palette()
        self.setWindowIcon(self._make_app_icon(theme))
        self._tray.setIcon(self._make_app_icon(theme))
        self._close_button.setIcon(self._make_close_icon(theme))
        self._help_popup.setText(self._help_html())
        self._donate_popup.setText(self._donate_html())
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
        search_field.setPlaceholderText("Search all drives...")
        search_field.setFixedHeight(self._search_height)
        search_field.textChanged.connect(self._on_text_changed)
        search_field.returnPressed.connect(self._activate_selected)
        search_field.installEventFilter(self)
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
        button.setToolTip("")
        button.setFixedSize(self._search_height - 12, self._search_height - 12)
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

    def _build_result_list(self) -> QListView:
        self._result_model = _ResultModel(self._recency, self)
        result_list = QListView()
        result_list.setObjectName("resultList")
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
        label.setText(self._help_html())
        label.hide()
        return label

    def _help_html(self) -> str:
        theme = self._theme
        cap = f"background-color:{theme.outline}; color:{theme.on_surface};"
        key_sep = f'<span style="color:{theme.on_surface_variant};"> / </span>'
        desc_style = f"color:{theme.on_surface_variant};"
        groups: list[list[tuple[tuple[str, ...], str]]] = [[]]
        for entry in _HELP_SHORTCUTS:
            if entry is None:
                groups.append([])
            else:
                groups[-1].append(entry)
        left_group, right_group, bottom_group = [*groups, [], []][:3]

        def render_cells(group: list[tuple[tuple[str, ...], str]], index: int) -> str:
            if index >= len(group):
                return "<td></td><td></td>"
            keys, description = group[index]
            caps = [f'<span style="{cap}">&nbsp;{k}&nbsp;</span>' for k in keys]
            return (
                f'<td align="right" style="padding:3px 0;">{key_sep.join(caps)}</td>'
                f'<td style="{desc_style} padding:3px 8px;">{description}</td>'
            )

        divider_col = f'<td style="border-left:1px solid {theme.outline}; padding:0 8px;"></td>'
        max_rows = max(len(left_group), len(right_group))
        rows = [
            f"<tr>{render_cells(left_group, i)}{divider_col}{render_cells(right_group, i)}</tr>"
            for i in range(max_rows)
        ]
        if bottom_group:
            hr_style = f"border:none; border-top:1px solid {theme.outline};"
            divider_row = f'<tr><td colspan="5"><hr style="{hr_style}"></td></tr>'
            rows.append(divider_row)
            for keys, description in bottom_group:
                caps = [f'<span style="{cap}">&nbsp;{k}&nbsp;</span>' for k in keys]
                rows.append(
                    f'<tr><td colspan="5" align="center" style="padding:3px 0;">'
                    f"{key_sep.join(caps)}"
                    f'<span style="{desc_style}"> {description}</span>'
                    f"</td></tr>"
                )
        return f'<table cellspacing="2" align="center">{"".join(rows)}</table>'

    def _build_donate_popup(self) -> QLabel:
        label = QLabel()
        label.setObjectName("donatePopup")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self._on_donate_link)
        label.setText(self._donate_html())
        label.hide()
        return label

    def _donate_html(self) -> str:
        theme = self._theme
        badge = f"background-color:{theme.outline}; color:{theme.on_surface}; text-decoration:none;"
        web_links = [f'<a href="{url}" style="{badge}">&nbsp;{label}&nbsp;</a>' for label, url in _DONATE_WEB]
        crypto_links = [
            f'<a href="copy:{address}" style="{badge}">&nbsp;{label}&nbsp;</a>' for label, address in _DONATE_CRYPTO
        ]
        return (
            '<table width="100%" cellspacing="4" cellpadding="0">'
            f'<tr><td align="center">{"&ensp;".join(web_links)}</td></tr>'
            f'<tr><td align="center">{"&ensp;".join(crypto_links)}</td></tr>'
            "</table>"
        )

    def _on_donate_link(self, url: str) -> None:
        self._help_hide_timer.stop()
        self._drag_pos = None
        if url.startswith("copy:"):
            address = url.removeprefix("copy:")
            QApplication.clipboard().setText(address)
            self._show_temp_status("Copied!", 2000)
        else:
            self._hide_popups()
            QDesktopServices.openUrl(QUrl(url))

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._MARGIN, self._MARGIN, self._MARGIN, self._MARGIN)
        outer.addWidget(self._card)

    @staticmethod
    def _menu_qss(theme: Theme) -> str:
        return f"""
            QMenu {{
                background-color: {theme.surface_variant};
                color: {theme.on_surface};
                border: 1px solid {theme.outline};
                border-radius: 8px;
                padding: 4px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                font-size: 9pt;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {theme.hover};
            }}
        """

    def _apply_styles(self) -> None:
        theme = self._theme
        menu_qss = self._menu_qss(theme)
        if hasattr(self, "_tray"):
            tray_menu = self._tray.contextMenu()
            if tray_menu is not None:
                tray_menu.setStyleSheet(menu_qss)
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
                font-size: 11pt;
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
                font-size: 8pt;
                font-family: "{_FONT_FAMILY}", sans-serif;
                padding: 0;
                background-color: transparent;
            }}
            #closeButton {{
                background-color: transparent;
                border: none;
                border-radius: {(self._search_height - 12) // 2}px;
            }}
            #closeButton:hover {{
                background-color: {theme.hover};
            }}
            #closeButton:pressed {{
                background-color: {theme.outline};
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
            QScrollBar:vertical:hover {{
                width: 10px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.outline};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                border-radius: 5px;
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
                font-size: 9pt;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {theme.hover};
            }}
            #helpPopup, #donatePopup {{
                background-color: {theme.surface_variant};
                color: {theme.on_surface};
                border: none;
                padding: 12px 16px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                font-size: 9pt;
            }}
        """)

    def _sync_height(self, *, animate: bool = False) -> None:
        self._height_anim.stop()
        count = self._result_model.rowCount()
        has_results = count > 0
        help_visible = not self._help_popup.isHidden()
        donate_visible = not self._donate_popup.isHidden()
        popup_visible = help_visible or donate_visible

        self._result_list.setVisible(has_results and not popup_visible)
        self._separator.setVisible(has_results or popup_visible)
        has_content = has_results or popup_visible
        self._card_layout.setContentsMargins(0, 0, 0, self._RADIUS if has_content else 0)

        if popup_visible:
            popup = self._help_popup if help_visible else self._donate_popup
            popup_height = popup.sizeHint().height()
            card_height = self._search_height + 1 + popup_height + self._RADIUS
        elif has_results:
            visible = min(count, self._MAX_VISIBLE)
            self._result_list.setFixedHeight(visible * self._delegate.item_height)
            card_height = self._search_height + 1 + visible * self._delegate.item_height + self._RADIUS
        else:
            card_height = self._search_height

        target = card_height + self._MARGIN * 2
        if animate and target > self.height():
            self._height_target = target
            self._height_anim.setStartValue(self.height())
            self._height_anim.setEndValue(target)
            self._height_anim.start()
        else:
            self._set_height_preserving_pos(target)

    def _set_height_preserving_pos(self, height: int) -> None:
        pos = self.pos()
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
            elif self._drag_pos is not None:
                if event_type == QEvent.Type.MouseMove:
                    mouse_event = cast("QMouseEvent", event)
                    self.move(mouse_event.globalPosition().toPoint() - self._drag_pos)
                    return True
                if event_type == QEvent.Type.MouseButtonRelease:
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
            case Qt.Key.Key_Down | Qt.Key.Key_Up | Qt.Key.Key_PageDown | Qt.Key.Key_PageUp:
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
        self._help_popup.hide()
        self._donate_popup.hide()
        if not text.strip():
            self._debounce_timer.stop()
            self._stop_search()
            self._stop_searching_animation()
            self._result_model.clear()
            self._status_label.clear()
            self._sync_height()
            return
        self._stop_search()
        self._start_searching_animation()
        self._debounce_timer.start()

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
            self._save_window_position(self.pos())
            event.ignore()
            self.hide()
        else:
            self._save_window_position(self.pos())
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
        if self._help_popup.isHidden() and self._donate_popup.isHidden():
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
        if self._help_popup.isHidden() and self._donate_popup.isHidden():
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
        menu = QMenu(self)
        file_icon = QIcon(self._delegate.file_icon)
        folder_icon = QIcon(self._delegate.folder_icon)
        act_open = QAction(file_icon, "Open file", self)
        act_open.triggered.connect(lambda: self._open_file_by_path(path))
        act_folder = QAction(folder_icon, "Open containing folder", self)
        act_folder.triggered.connect(lambda: self._open_folder(path))
        menu.addAction(act_open)
        menu.addAction(act_folder)
        menu.popup(self._result_list.mapToGlobal(pos))

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
        self._help_popup.setVisible(was_hidden)
        self._sync_height(animate=was_hidden)
        if was_hidden:
            self._help_hide_timer.start()
        else:
            self._help_hide_timer.stop()

    def _toggle_donate(self) -> None:
        was_hidden = self._donate_popup.isHidden()
        self._help_popup.hide()
        self._donate_popup.setVisible(was_hidden)
        self._sync_height(animate=was_hidden)
        if was_hidden:
            self._help_hide_timer.start()
        else:
            self._help_hide_timer.stop()

    def _hide_popups(self) -> None:
        changed = False
        if not self._help_popup.isHidden():
            self._help_popup.hide()
            changed = True
        if not self._donate_popup.isHidden():
            self._donate_popup.hide()
            changed = True
        if changed:
            self._sync_height()

    # -- system tray --

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self._make_app_icon(self._theme), self)
        menu = QMenu()
        act_toggle = QAction("Show / Hide", self)
        act_toggle.triggered.connect(self._toggle_visibility)
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_toggle)
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        return tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def _toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            if sys.platform == "win32":
                # noinspection PyUnresolvedReferences
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _quit_app(self) -> None:
        self._save_window_position(self.pos())
        self._stop_search()
        if _hotkey is not None and self._hotkey_registered:
            _hotkey.unregister_hotkey()
            app = QApplication.instance()
            if app is not None and self._hotkey_filter is not None:
                app.removeNativeEventFilter(self._hotkey_filter)
        self._tray.hide()
        QApplication.quit()

    # -- global hotkey --

    def _init_hotkey(self) -> None:
        self._hotkey_registered = False
        self._hotkey_filter: QAbstractNativeEventFilter | None = None
        if _hotkey is None:
            return
        self._hotkey_registered = _hotkey.register_hotkey()
        if not self._hotkey_registered:
            return
        self._hotkey_filter = _HotkeyFilter(self._toggle_visibility)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._hotkey_filter)


def main() -> None:  # pragma: no cover - entry point starts Qt event loop, not unit-testable
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
