"""Export the Seekbar application icon to assets/seekbar.ico."""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, Qt

ICON_COLOR = "#BB86FC"
ICON_SIZES = (16, 32, 48, 256)


def render_icon(size: int, color_hex: str) -> QImage:
    """Render a magnifying glass icon at the given pixel size."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / 32.0
    color = QColor(color_hex)
    painter.setPen(QPen(color, 2.0 * scale))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy, radius = 12.0 * scale, 12.0 * scale, 8.0 * scale
    painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))
    painter.setPen(QPen(color, 2.5 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    handle_x, handle_y = cx + radius * 0.707, cy + radius * 0.707
    painter.drawLine(int(handle_x), int(handle_y), int(handle_x + 7 * scale), int(handle_y + 7 * scale))
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
        width = 0 if image.width() >= 256 else image.width()
        height = 0 if image.height() >= 256 else image.height()
        entry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(png_data), data_offset)
        directory_entries.append(entry)
        png_payloads.append(png_data)
        data_offset += len(png_data)

    with open(output_path, "wb") as ico_file:
        ico_file.write(header)
        for entry in directory_entries:
            ico_file.write(entry)
        for payload in png_payloads:
            ico_file.write(payload)


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - QPainter requires a live QGuiApplication instance
    images = [render_icon(size, ICON_COLOR) for size in ICON_SIZES]

    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    ico_path = assets_dir / "seekbar.ico"
    write_ico(images, ico_path)
    print(f"Wrote {ico_path} ({ico_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
