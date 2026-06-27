import ctypes
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QSocketNotifier

if TYPE_CHECKING:
    from collections.abc import Callable

if sys.platform != "linux":  # pragma: no cover - Linux-only module
    msg = "This module is only available on Linux"
    raise ImportError(msg)

# X11 protocol constants (see X.h / keysymdef.h).
_KEY_PRESS = 2
_GRAB_MODE_ASYNC = 1
_XK_S = 0x0073  # XK_s keysym (lowercase 's')
_CONTROL_MASK = 1 << 2  # ControlMask
_MOD1_MASK = 1 << 3  # Mod1Mask -> the Alt key
_LOCK_MASK = 1 << 1  # CapsLock
_MOD2_MASK = 1 << 4  # NumLock
_MODIFIERS = _CONTROL_MASK | _MOD1_MASK
# XGrabKey is modifier-exact, so the combo is grabbed under every lock-key state; otherwise it
# silently fails whenever CapsLock or NumLock happens to be on.
_LOCK_VARIANTS = (0, _LOCK_MASK, _MOD2_MASK, _LOCK_MASK | _MOD2_MASK)
_XEVENT_SIZE = 192  # sizeof(XEvent) on 64-bit; only the leading int `type` field is read


def _load_xlib() -> ctypes.CDLL | None:
    try:
        xlib = ctypes.CDLL("libX11.so.6")
    except OSError:  # libX11 absent (rare on desktops); the global hotkey is simply unavailable
        return None
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = (ctypes.c_char_p,)
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XDefaultRootWindow.argtypes = (ctypes.c_void_p,)
    xlib.XKeysymToKeycode.restype = ctypes.c_ubyte
    xlib.XKeysymToKeycode.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    xlib.XGrabKey.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    )
    xlib.XConnectionNumber.restype = ctypes.c_int
    xlib.XConnectionNumber.argtypes = (ctypes.c_void_p,)
    xlib.XPending.restype = ctypes.c_int
    xlib.XPending.argtypes = (ctypes.c_void_p,)
    xlib.XNextEvent.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    xlib.XSync.argtypes = (ctypes.c_void_p, ctypes.c_int)
    xlib.XCloseDisplay.argtypes = (ctypes.c_void_p,)
    return xlib


_xlib = _load_xlib()


class _State:
    display: int | None = None
    notifier: QSocketNotifier | None = None
    callback: Callable[[], object] | None = None


_state = _State()


def register_hotkey(callback: Callable[[], object]) -> bool:
    if _xlib is None:
        return False
    display = _xlib.XOpenDisplay(None)
    if not display:  # no X server reachable (Wayland-only session or headless)
        return False
    keycode = _xlib.XKeysymToKeycode(display, _XK_S)
    if keycode == 0:
        _xlib.XCloseDisplay(display)
        return False
    root = _xlib.XDefaultRootWindow(display)
    for lock in _LOCK_VARIANTS:
        _xlib.XGrabKey(display, keycode, _MODIFIERS | lock, root, 0, _GRAB_MODE_ASYNC, _GRAB_MODE_ASYNC)
    _xlib.XSync(display, 0)
    notifier = QSocketNotifier(_xlib.XConnectionNumber(display), QSocketNotifier.Type.Read)
    notifier.activated.connect(_on_activated)
    _state.display = display
    _state.notifier = notifier
    _state.callback = callback
    return True


def _on_activated() -> None:
    if _xlib is None or _state.display is None or _state.callback is None:
        return
    event = ctypes.create_string_buffer(_XEVENT_SIZE)
    while _xlib.XPending(_state.display) > 0:
        _xlib.XNextEvent(_state.display, event)
        if ctypes.c_int.from_buffer_copy(event).value == _KEY_PRESS:  # XEvent.type, native byte order
            _state.callback()


def unregister_hotkey() -> None:
    if _state.notifier is not None:
        _state.notifier.setEnabled(False)
        _state.notifier = None
    if _xlib is not None and _state.display is not None:
        _xlib.XCloseDisplay(_state.display)  # closing the connection releases all key grabs
        _state.display = None
    _state.callback = None
