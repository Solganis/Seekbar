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


@dataclasses.dataclass(frozen=True, slots=True)
class Accent:
    label: str
    primary_dark: str
    primary_light: str
    selected_dark: str
    selected_light: str


class TrayIconMode(enum.Enum):
    AUTO = "auto"
    WHITE = "white"
    BLACK = "black"
    ACCENT = "accent"


DARK_THEME = Theme(
    surface="#1E1E1E",
    surface_variant="#2C2C2C",
    on_surface="#E0E0E0",
    on_surface_variant="#959595",
    primary="#9FB4C8",
    outline="#333333",
    hover="#252525",
    selected="#2E3640",
    folder_color="#B39B6E",
    file_color="#707070",
    file_fold_color="#808080",
)

LIGHT_THEME = Theme(
    surface="#F5F5F5",
    surface_variant="#E8E8E8",
    on_surface="#1C1C1C",
    on_surface_variant="#595959",
    primary="#4A5A6E",
    outline="#C8C8C8",
    hover="#ECECEC",
    selected="#DCE3EC",
    folder_color="#8B7340",
    file_color="#808080",
    file_fold_color="#909090",
)


# The "slate" preset intentionally mirrors the base themes above, so the default accent reproduces them.
ACCENTS: dict[str, Accent] = {
    "teal": Accent("Teal", "#5CD0C4", "#1E7A6E", "#26403C", "#CFEAE5"),
    "green": Accent("Green", "#7CD89A", "#3F7D54", "#2A3D31", "#D8EEDD"),
    "cyan": Accent("Cyan", "#5CC6E0", "#1C6E86", "#243C42", "#CFE9F0"),
    "blue": Accent("Blue", "#86B8FC", "#3A5DA8", "#2A3340", "#DCE6F8"),
    "slate": Accent("Slate", "#9FB4C8", "#4A5A6E", "#2E3640", "#DCE3EC"),
    "violet": Accent("Violet", "#BB86FC", "#6750A4", "#332D41", "#E8DEF8"),
    "rose": Accent("Rose", "#F08FB0", "#A83D5E", "#402932", "#F6DDE6"),
    "amber": Accent("Amber", "#E6B968", "#7E5F18", "#403628", "#F0E6CF"),
}
DEFAULT_ACCENT = "slate"


_SRGB_LINEAR_THRESHOLD = 0.04045
_DARK_LUMINANCE_THRESHOLD = 0.5


def _linearize(srgb: float) -> float:
    if srgb <= _SRGB_LINEAR_THRESHOLD:
        return srgb / 12.92
    return float(((srgb + 0.055) / 1.055) ** 2.4)


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


def is_dark(theme: Theme) -> bool:
    return _relative_luminance(theme.surface) < _DARK_LUMINANCE_THRESHOLD


def _resolve_base(mode: ThemeMode) -> Theme:
    match mode:
        case ThemeMode.DARK:
            return DARK_THEME
        case ThemeMode.LIGHT:
            return LIGHT_THEME
        case ThemeMode.AUTO:  # pragma: no branch - exhaustive over ThemeMode, no-match arm unreachable
            raw_app = QGuiApplication.instance()
            if raw_app is not None:
                app = cast("QGuiApplication", raw_app)
                scheme = app.styleHints().colorScheme()
                if scheme == Qt.ColorScheme.Light:
                    return LIGHT_THEME
            return DARK_THEME


def resolve_theme(mode: ThemeMode, accent_id: str = DEFAULT_ACCENT) -> Theme:
    base = _resolve_base(mode)
    accent = ACCENTS.get(accent_id, ACCENTS[DEFAULT_ACCENT])
    if base is DARK_THEME:
        return dataclasses.replace(base, primary=accent.primary_dark, selected=accent.selected_dark)
    return dataclasses.replace(base, primary=accent.primary_light, selected=accent.selected_light)
