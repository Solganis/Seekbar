from typing import TYPE_CHECKING, override

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from seekbar.constants import _FONT_FAMILY, _ICON_SIZE, _IS_DIR_ROLE, _NAME_ROLE, _PARENT_ROLE
from seekbar.filetypes import FileCategory, categorize

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtCore import QModelIndex, QPersistentModelIndex
    from PySide6.QtWidgets import QStyleOptionViewItem, QWidget

    from seekbar.theme import Theme


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
        self._icons = self._build_icons()

    @property
    def item_height(self) -> int:
        return self._item_height

    @property
    def folder_icon(self) -> QPixmap:
        return self._icons[FileCategory.FOLDER]

    @property
    def file_icon(self) -> QPixmap:
        return self._icons[FileCategory.GENERIC]

    def icon_for(self, name: str, *, is_dir: bool) -> QPixmap:
        category = FileCategory.FOLDER if is_dir else categorize(name)
        return self._icons[category]

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._icons = self._build_icons()

    def _build_icons(self) -> dict[FileCategory, QPixmap]:
        builders: dict[FileCategory, Callable[[QPainter], None]] = {
            FileCategory.FOLDER: self._draw_folder,
            FileCategory.GENERIC: self._draw_page,
            FileCategory.DOCUMENT: self._draw_document,
            FileCategory.PDF: self._draw_pdf,
            FileCategory.SHEET: self._draw_sheet,
            FileCategory.CODE: self._draw_code,
            FileCategory.IMAGE: self._draw_image,
            FileCategory.VIDEO: self._draw_video,
            FileCategory.AUDIO: self._draw_audio,
            FileCategory.ARCHIVE: self._draw_archive,
            FileCategory.EXECUTABLE: self._draw_executable,
        }
        return {category: self._render(draw) for category, draw in builders.items()}

    @staticmethod
    def _render(draw: Callable[[QPainter], None]) -> QPixmap:
        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw(painter)
        painter.end()
        return pixmap

    @staticmethod
    def _erase(painter: QPainter, path: QPainterPath, stroke: float = 0.0) -> None:
        # Punch the detail out as transparent negative space so every glyph stays a single flat tint.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        if stroke > 0:
            pen = QPen(QColor(0, 0, 0), stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.strokePath(path, pen)
        else:
            painter.fillPath(path, QColor(0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _fill(self, painter: QPainter, path: QPainterPath) -> None:
        painter.fillPath(path, QColor(self._theme.file_color))

    def _draw_folder(self, painter: QPainter) -> None:
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

    def _draw_page(self, painter: QPainter) -> None:
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

    def _draw_document(self, painter: QPainter) -> None:
        self._draw_page(painter)
        lines = QPainterPath()
        for line_y in (9, 12, 15):
            lines.moveTo(6, line_y)
            lines.lineTo(14, line_y)
        self._erase(painter, lines, stroke=1.4)

    def _draw_pdf(self, painter: QPainter) -> None:
        self._draw_page(painter)
        line = QPainterPath()
        line.moveTo(6, 8.5)
        line.lineTo(11, 8.5)
        self._erase(painter, line, stroke=1.4)
        badge = QPainterPath()
        badge.addRoundedRect(5.5, 11.5, 9, 5, 1.2, 1.2)
        self._erase(painter, badge)

    def _draw_sheet(self, painter: QPainter) -> None:
        self._draw_page(painter)
        grid = QPainterPath()
        for row_y in (8, 11.5, 15):
            grid.moveTo(5.5, row_y)
            grid.lineTo(14.5, row_y)
        for column_x in (8.7, 11.3):
            grid.moveTo(column_x, 8)
            grid.lineTo(column_x, 16.5)
        self._erase(painter, grid, stroke=1.0)

    def _draw_code(self, painter: QPainter) -> None:
        self._draw_page(painter)
        chevrons = QPainterPath()
        chevrons.moveTo(9, 7.5)
        chevrons.lineTo(6, 11)
        chevrons.lineTo(9, 14.5)
        chevrons.moveTo(11.5, 7.5)
        chevrons.lineTo(14.5, 11)
        chevrons.lineTo(11.5, 14.5)
        self._erase(painter, chevrons, stroke=1.4)

    def _draw_image(self, painter: QPainter) -> None:
        frame = QPainterPath()
        frame.addRoundedRect(2, 3, 16, 14, 2.5, 2.5)
        self._fill(painter, frame)
        window = QPainterPath()
        window.addRoundedRect(4, 5, 12, 10, 1.2, 1.2)
        self._erase(painter, window)
        sun = QPainterPath()
        sun.addEllipse(5.6, 6.2, 2.8, 2.8)
        self._fill(painter, sun)
        mountains = QPainterPath()
        mountains.moveTo(4, 15)
        mountains.lineTo(8, 9.5)
        mountains.lineTo(10.5, 12.5)
        mountains.lineTo(12.5, 10)
        mountains.lineTo(16, 15)
        mountains.closeSubpath()
        self._fill(painter, mountains)

    def _draw_video(self, painter: QPainter) -> None:
        frame = QPainterPath()
        frame.addRoundedRect(2, 4, 16, 12, 2.5, 2.5)
        self._fill(painter, frame)
        play = QPainterPath()
        play.moveTo(8.5, 7.5)
        play.lineTo(8.5, 12.5)
        play.lineTo(12.5, 10)
        play.closeSubpath()
        self._erase(painter, play)

    def _draw_audio(self, painter: QPainter) -> None:
        head = QPainterPath()
        head.addEllipse(4.5, 12, 4.4, 3.4)
        self._fill(painter, head)
        stem = QPainterPath()
        stem.addRect(8.4, 4.5, 1.4, 9.5)
        self._fill(painter, stem)
        flag = QPainterPath()
        flag.moveTo(9.8, 4.5)
        flag.lineTo(14, 6.3)
        flag.lineTo(14, 9)
        flag.lineTo(9.8, 7.2)
        flag.closeSubpath()
        self._fill(painter, flag)

    def _draw_archive(self, painter: QPainter) -> None:
        box = QPainterPath()
        box.addRoundedRect(3, 3.5, 14, 13, 2, 2)
        self._fill(painter, box)
        lid = QPainterPath()
        lid.moveTo(3, 8)
        lid.lineTo(17, 8)
        self._erase(painter, lid, stroke=1.2)
        latch = QPainterPath()
        latch.addRect(8.5, 9.5, 3, 3.2)
        self._erase(painter, latch)

    def _draw_executable(self, painter: QPainter) -> None:
        tiles = QPainterPath()
        tiles.addRoundedRect(3, 3, 6, 6, 1.4, 1.4)
        tiles.addRoundedRect(11, 3, 6, 6, 1.4, 1.4)
        tiles.addRoundedRect(3, 11, 6, 6, 1.4, 1.4)
        tiles.addRoundedRect(11, 11, 6, 6, 1.4, 1.4)
        self._fill(painter, tiles)

    @override
    def paint(  # pragma: no cover - Qt paint events cannot be triggered reliably in headless tests
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        display_name = index.data(_NAME_ROLE)
        if not display_name:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(self._theme.selected))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(self._theme.hover))

        is_dir = index.data(_IS_DIR_ROLE)
        icon = self.icon_for(display_name, is_dir=is_dir)
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
        elided = self._name_metrics.elidedText(display_name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        painter.setFont(self._path_font)
        painter.setPen(QColor(self._theme.on_surface_variant))
        path_rect = QRect(left, option.rect.top() + pad + name_h + pad, width, path_h + pad)
        parent_name = index.data(_PARENT_ROLE)
        elided = self._path_metrics.elidedText(parent_name, Qt.TextElideMode.ElideRight, width)
        painter.drawText(path_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        painter.restore()

    @override
    def sizeHint(self, _option: QStyleOptionViewItem, _index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(0, self._item_height)
