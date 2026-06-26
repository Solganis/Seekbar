from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication

from seekbar.constants import SETTINGS_APP, SETTINGS_ORG
from seekbar.theme import ACCENTS, DEFAULT_ACCENT, ThemeMode, TrayIconMode


def load_theme_mode() -> ThemeMode:
    raw = QSettings(SETTINGS_ORG, SETTINGS_APP).value("theme_mode", ThemeMode.AUTO.value)
    try:
        return ThemeMode(raw)
    except ValueError:
        return ThemeMode.AUTO


def save_theme_mode(mode: ThemeMode) -> None:
    QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("theme_mode", mode.value)


def load_accent() -> str:
    raw = QSettings(SETTINGS_ORG, SETTINGS_APP).value("accent", DEFAULT_ACCENT)
    return raw if isinstance(raw, str) and raw in ACCENTS else DEFAULT_ACCENT


def save_accent(accent_id: str) -> None:
    QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("accent", accent_id)


def load_tray_icon_mode() -> TrayIconMode:
    raw = QSettings(SETTINGS_ORG, SETTINGS_APP).value("tray_icon_mode", TrayIconMode.AUTO.value)
    try:
        return TrayIconMode(raw)
    except ValueError:
        return TrayIconMode.AUTO


def save_tray_icon_mode(mode: TrayIconMode) -> None:
    QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("tray_icon_mode", mode.value)


def load_window_position() -> QPoint | None:
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


def save_window_position(pos: QPoint) -> None:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.setValue("window_x", pos.x())
    settings.setValue("window_y", pos.y())
