import sys

if sys.platform != "win32":  # pragma: no cover - Windows-only module
    _err = "This module is only available on Windows"
    raise ImportError(_err)

# noinspection PyUnresolvedReferences
from ctypes import windll  # type: ignore[attr-defined] - Windows-only attribute

user32 = windll.user32

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
VK_S = 0x53
_HOTKEY_ID = 1


# noinspection PyUnresolvedReferences
def register_hotkey() -> bool:
    return bool(user32.RegisterHotKey(None, _HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_S))


# noinspection PyUnresolvedReferences
def unregister_hotkey() -> bool:
    return bool(user32.UnregisterHotKey(None, _HOTKEY_ID))
