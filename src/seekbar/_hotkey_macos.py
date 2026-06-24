import ctypes
import ctypes.util
import sys
from typing import TYPE_CHECKING

if sys.platform != "darwin":  # pragma: no cover - macOS-only module
    msg = "This module is only available on macOS"
    raise ImportError(msg)

if TYPE_CHECKING:
    from collections.abc import Callable

_carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))

# Constants verified against the Carbon HIToolbox SDK headers (Events.h / CarbonEvents.h).
_EVENT_CLASS_KEYBOARD = 0x6B657962  # 'keyb'
_EVENT_HOTKEY_PRESSED = 5
_OPTION_KEY = 1 << 11  # optionKey -> macOS "Alt"
_CONTROL_KEY = 1 << 12  # controlKey
_VK_ANSI_S = 0x01


class _EventHotKeyID(ctypes.Structure):
    _fields_ = (("signature", ctypes.c_uint32), ("id", ctypes.c_uint32))


class _EventTypeSpec(ctypes.Structure):
    _fields_ = (("event_class", ctypes.c_uint32), ("event_kind", ctypes.c_uint32))


# OSStatus handler(EventHandlerCallRef nextHandler, EventRef event, void *userData)
_HANDLER_PROTO = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

_carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
_carbon.InstallEventHandler.restype = ctypes.c_int32
_carbon.InstallEventHandler.argtypes = (
    ctypes.c_void_p,
    _HANDLER_PROTO,
    ctypes.c_uint32,
    ctypes.POINTER(_EventTypeSpec),
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
)
_carbon.RegisterEventHotKey.restype = ctypes.c_int32
_carbon.RegisterEventHotKey.argtypes = (
    ctypes.c_uint32,
    ctypes.c_uint32,
    _EventHotKeyID,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_void_p),
)
_carbon.UnregisterEventHotKey.restype = ctypes.c_int32
_carbon.UnregisterEventHotKey.argtypes = (ctypes.c_void_p,)
_carbon.RemoveEventHandler.restype = ctypes.c_int32
_carbon.RemoveEventHandler.argtypes = (ctypes.c_void_p,)

# Keep the CFUNCTYPE trampoline and refs alive for the process lifetime; GC would break the C handler.
_keepalive: list[object] = []
_handler_ref = ctypes.c_void_p()
_hotkey_ref = ctypes.c_void_p()


def register_hotkey(callback: Callable[[], object]) -> bool:
    def _on_hotkey(_caller: int, _event: int, _user: int) -> int:
        callback()
        return 0

    handler = _HANDLER_PROTO(_on_hotkey)
    spec = _EventTypeSpec(_EVENT_CLASS_KEYBOARD, _EVENT_HOTKEY_PRESSED)
    target = _carbon.GetApplicationEventTarget()
    if _carbon.InstallEventHandler(target, handler, 1, ctypes.byref(spec), None, ctypes.byref(_handler_ref)) != 0:
        return False
    hotkey_id = _EventHotKeyID(0x736B6272, 1)  # 'skbr'
    modifiers = _CONTROL_KEY | _OPTION_KEY
    if _carbon.RegisterEventHotKey(_VK_ANSI_S, modifiers, hotkey_id, target, 0, ctypes.byref(_hotkey_ref)) != 0:
        return False
    _keepalive.append(handler)
    return True


def unregister_hotkey() -> None:
    _carbon.UnregisterEventHotKey(_hotkey_ref)
    _carbon.RemoveEventHandler(_handler_ref)
