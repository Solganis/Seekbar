from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from seekbar.theme import TrayIconMode

if TYPE_CHECKING:
    from seekbar.theme import Theme


def make_app_icon(color_hex: str) -> QIcon:
    icon = QIcon()
    for size in (16, 32, 48):
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = size / 32.0
        color = QColor(color_hex)
        painter.setPen(QPen(color, 3.4 * scale))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy, radius = 12.0 * scale, 12.0 * scale, 8.0 * scale
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))
        painter.setPen(QPen(color, 4.0 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        hx, hy = cx + radius * 0.707, cy + radius * 0.707
        painter.drawLine(int(hx), int(hy), int(hx + 7 * scale), int(hy + 7 * scale))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def tint_icon(icon: QIcon, color: str, size: int = 16) -> QIcon:
    source = icon.pixmap(QSize(size, size))
    if source.isNull():
        return icon
    tinted = QPixmap(source.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return QIcon(tinted)


def make_close_icon(theme: Theme) -> QIcon:
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


def icon_color(mode: TrayIconMode, theme: Theme) -> str:
    match mode:
        case TrayIconMode.WHITE:
            return "#FFFFFF"
        case TrayIconMode.BLACK:
            return "#000000"
        case TrayIconMode.ACCENT:
            return theme.primary
        case TrayIconMode.AUTO:  # pragma: no branch - exhaustive over TrayIconMode, no-match arm unreachable
            return theme.on_surface
