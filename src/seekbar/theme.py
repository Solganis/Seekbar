import dataclasses
import enum
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


class ThemeMode(enum.Enum):
    AUTO = "auto"
    DARK = "dark"
    LIGHT = "light"


@dataclasses.dataclass(frozen=True, slots=True)
class Theme:
    surface: str
    surface_variant: str
    on_surface: str
    on_surface_variant: str
    primary: str
    outline: str
    hover: str
    selected: str
    folder_color: str
    file_color: str
    file_fold_color: str


DARK_THEME = Theme(
    surface="#1E1E1E",
    surface_variant="#2C2C2C",
    on_surface="#E0E0E0",
    on_surface_variant="#959595",
    primary="#BB86FC",
    outline="#333333",
    hover="#252525",
    selected="#332D41",
    folder_color="#B39B6E",
    file_color="#707070",
    file_fold_color="#808080",
)

LIGHT_THEME = Theme(
    surface="#F5F5F5",
    surface_variant="#E8E8E8",
    on_surface="#1C1C1C",
    on_surface_variant="#595959",
    primary="#6750A4",
    outline="#C8C8C8",
    hover="#ECECEC",
    selected="#E8DEF8",
    folder_color="#8B7340",
    file_color="#808080",
    file_fold_color="#909090",
)


_SRGB_LINEAR_THRESHOLD = 0.04045


def _linearize(srgb: float) -> float:
    if srgb <= _SRGB_LINEAR_THRESHOLD:
        return srgb / 12.92
    return ((srgb + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    red = _linearize(int(hex_color[1:3], 16) / 255)
    green = _linearize(int(hex_color[3:5], 16) / 255)
    blue = _linearize(int(hex_color[5:7], 16) / 255)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(color1: str, color2: str) -> float:
    lum1 = _relative_luminance(color1)
    lum2 = _relative_luminance(color2)
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def resolve_theme(mode: ThemeMode) -> Theme:
    match mode:
        case ThemeMode.DARK:
            return DARK_THEME
        case ThemeMode.LIGHT:
            return LIGHT_THEME
        case ThemeMode.AUTO:
            raw_app = QGuiApplication.instance()
            if raw_app is not None:
                app = cast("QGuiApplication", raw_app)
                scheme = app.styleHints().colorScheme()
                if scheme == Qt.ColorScheme.Light:
                    return LIGHT_THEME
            return DARK_THEME
