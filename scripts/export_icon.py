"""Export the Seekbar application icons: Windows .ico, macOS .icns, and a source .png.

The icon is a white magnifying glass on a dark rounded tile. The dark tile keeps the mark
legible on any background (Explorer/Finder light mode included), where a bare white glass on
a transparent background would vanish. The dark shade matches DARK_THEME.surface.
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QLineF, QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, Qt

GLASS_COLOR = "#FFFFFF"
BACKGROUND_COLOR = "#1E1E1E"

ICO_SIZES = (16, 32, 48, 256)
# ICNS PNG-based entries: (OSType, pixel size). These cover the Dock and Finder at 1x and 2x.
ICNS_ENTRIES = (
    (b"ic11", 32),
    (b"ic12", 64),
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic09", 512),
    (b"ic10", 1024),
)
PNG_SOURCE_SIZE = 256

# In an ICO directory entry width/height are single bytes; the value 0 encodes a 256 px dimension.
ICO_DIMENSION_LIMIT = 256

# The glass is drawn in a 32-unit design space; these constants scale-and-center its antialiased
# bounding box inside each tile so the padding around it is even at every export size.
_GLASS_BBOX_CENTER = 14.48
_GLASS_BBOX_EXTENT = 24.36
_GLASS_TILE_FRACTION = 0.62  # the glass spans 62% of the tile, leaving the rest as padding
_TILE_CORNER_FRACTION = 0.22


def _draw_glass(painter: QPainter) -> None:
    """Stroke the magnifying glass in the 32-unit design space at the painter's current transform."""
    center, radius = 12.0, 8.0
    painter.setPen(QPen(QColor(GLASS_COLOR), 3.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(center - radius, center - radius, radius * 2, radius * 2))
    painter.setPen(QPen(QColor(GLASS_COLOR), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    handle_start = center + radius * 0.7071
    painter.drawLine(QLineF(handle_start, handle_start, handle_start + 7, handle_start + 7))


def render_icon(size: int) -> QImage:
    """Render a white magnifying glass on a dark rounded tile at the given pixel size."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    corner = size * _TILE_CORNER_FRACTION
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BACKGROUND_COLOR))
    painter.drawRoundedRect(QRectF(0, 0, size, size), corner, corner)

    scale = size * _GLASS_TILE_FRACTION / _GLASS_BBOX_EXTENT
    painter.translate(size / 2, size / 2)
    painter.scale(scale, scale)
    painter.translate(-_GLASS_BBOX_CENTER, -_GLASS_BBOX_CENTER)
    _draw_glass(painter)

    painter.end()
    return image


def image_to_png_bytes(image: QImage) -> bytes:
    """Serialize a QImage to PNG bytes."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")  # ty: ignore[no-matching-overload] - PySide6 stub types format as bytes, needs str
    png_data = bytes(buffer.data().data())
    buffer.close()
    return png_data


def write_ico(images: list[QImage], output_path: Path) -> None:
    """Write multiple QImage frames into a Windows .ico file (PNG-encoded)."""
    frame_count = len(images)
    header = struct.pack("<HHH", 0, 1, frame_count)

    directory_entries: list[bytes] = []
    png_payloads: list[bytes] = []
    data_offset = 6 + frame_count * 16

    for image in images:
        png_data = image_to_png_bytes(image)
        width = 0 if image.width() >= ICO_DIMENSION_LIMIT else image.width()
        height = 0 if image.height() >= ICO_DIMENSION_LIMIT else image.height()
        entry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(png_data), data_offset)
        directory_entries.append(entry)
        png_payloads.append(png_data)
        data_offset += len(png_data)

    with output_path.open("wb") as ico_file:
        ico_file.write(header)
        ico_file.writelines(directory_entries)
        ico_file.writelines(png_payloads)


def write_icns(entries: list[tuple[bytes, bytes]], output_path: Path) -> None:
    """Write PNG-encoded frames into a macOS .icns file."""
    body = b"".join(ostype + struct.pack(">I", len(png) + 8) + png for ostype, png in entries)
    output_path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - QPainter requires a live QGuiApplication instance
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(exist_ok=True)

    ico_path = assets_dir / "seekbar.ico"
    write_ico([render_icon(size) for size in ICO_SIZES], ico_path)
    print(f"Wrote {ico_path} ({ico_path.stat().st_size} bytes)")

    icns_path = assets_dir / "seekbar.icns"
    write_icns([(ostype, image_to_png_bytes(render_icon(px))) for ostype, px in ICNS_ENTRIES], icns_path)
    print(f"Wrote {icns_path} ({icns_path.stat().st_size} bytes)")

    png_path = assets_dir / "seekbar.png"
    png_path.write_bytes(image_to_png_bytes(render_icon(PNG_SOURCE_SIZE)))
    print(f"Wrote {png_path} ({png_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
