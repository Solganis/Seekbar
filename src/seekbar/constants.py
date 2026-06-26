import platform

from PySide6.QtCore import Qt

_IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1
_NAME_ROLE = Qt.ItemDataRole.UserRole + 2
_PARENT_ROLE = Qt.ItemDataRole.UserRole + 3


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
