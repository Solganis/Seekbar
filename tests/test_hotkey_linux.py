import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest
from assertpy2 import assert_that


def _import_under_linux(monkeypatch: pytest.MonkeyPatch):
    # The module is Linux-only (platform guard + libX11), but its logic is fully mockable. Importing it
    # under a faked "linux" platform lets the tests run on any OS; off Linux libX11 is absent, so the
    # module-level _xlib handle is simply None (every test patches _xlib anyway).
    monkeypatch.setattr(sys, "platform", "linux")
    sys.modules.pop("seekbar._hotkey_linux", None)
    return importlib.import_module("seekbar._hotkey_linux")


class TestImportGuard:
    def test_non_linux_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "platform", "win32")
        sys.modules.pop("seekbar._hotkey_linux", None)
        assert_that(lambda: importlib.import_module("seekbar._hotkey_linux")).raises(
            ImportError
        ).when_called_with().matches("Linux")


@pytest.fixture
def hotkey_linux(monkeypatch: pytest.MonkeyPatch):
    module = _import_under_linux(monkeypatch)
    module._state.display = None
    module._state.notifier = None
    module._state.callback = None
    yield module
    module._state.display = None
    module._state.notifier = None
    module._state.callback = None
    sys.modules.pop("seekbar._hotkey_linux", None)


class TestHotkeyLinux:
    def test_register_success(self, hotkey_linux):
        fake = MagicMock()
        fake.XOpenDisplay.return_value = 0xABC
        fake.XKeysymToKeycode.return_value = 39
        fake.XConnectionNumber.return_value = 7
        callback = MagicMock()
        with patch.object(hotkey_linux, "_xlib", fake), patch.object(hotkey_linux, "QSocketNotifier") as mock_notifier:
            result = hotkey_linux.register_hotkey(callback)
        assert_that(result).is_true()
        assert_that(fake.XGrabKey.call_count).is_equal_to(4)  # one grab per lock-mask variant
        mock_notifier.return_value.activated.connect.assert_called_once()
        assert_that(hotkey_linux._state.callback).is_same_as(callback)

    def test_register_without_xlib(self, hotkey_linux):
        with patch.object(hotkey_linux, "_xlib", None):
            assert_that(hotkey_linux.register_hotkey(MagicMock())).is_false()

    def test_register_without_display(self, hotkey_linux):
        fake = MagicMock()
        fake.XOpenDisplay.return_value = 0
        with patch.object(hotkey_linux, "_xlib", fake):
            assert_that(hotkey_linux.register_hotkey(MagicMock())).is_false()

    def test_register_without_keycode(self, hotkey_linux):
        fake = MagicMock()
        fake.XOpenDisplay.return_value = 0xABC
        fake.XKeysymToKeycode.return_value = 0
        with patch.object(hotkey_linux, "_xlib", fake):
            assert_that(hotkey_linux.register_hotkey(MagicMock())).is_false()
        fake.XCloseDisplay.assert_called_once()

    def test_on_activated_fires_on_keypress(self, hotkey_linux):
        fake = MagicMock()
        fake.XPending.side_effect = [1, 1, 0]

        def fill(_display, buffer):
            buffer[0:4] = hotkey_linux._KEY_PRESS.to_bytes(4, sys.byteorder)

        fake.XNextEvent.side_effect = fill
        callback = MagicMock()
        with patch.object(hotkey_linux, "_xlib", fake):
            hotkey_linux._state.display = 0xABC
            hotkey_linux._state.callback = callback
            hotkey_linux._on_activated()
        assert_that(callback.call_count).is_equal_to(2)

    def test_on_activated_ignores_non_keypress(self, hotkey_linux):
        fake = MagicMock()
        fake.XPending.side_effect = [1, 0]

        def fill(_display, buffer):
            buffer[0:4] = (3).to_bytes(4, sys.byteorder)  # KeyRelease, not KeyPress

        fake.XNextEvent.side_effect = fill
        callback = MagicMock()
        with patch.object(hotkey_linux, "_xlib", fake):
            hotkey_linux._state.display = 0xABC
            hotkey_linux._state.callback = callback
            hotkey_linux._on_activated()
        callback.assert_not_called()

    def test_on_activated_noop_when_inactive(self, hotkey_linux):
        fake = MagicMock()
        with patch.object(hotkey_linux, "_xlib", fake):
            hotkey_linux._on_activated()  # display/callback unset -> early return
        fake.XPending.assert_not_called()

    def test_unregister_releases(self, hotkey_linux):
        fake = MagicMock()
        notifier = MagicMock()
        with patch.object(hotkey_linux, "_xlib", fake):
            hotkey_linux._state.display = 0xABC
            hotkey_linux._state.notifier = notifier
            hotkey_linux._state.callback = MagicMock()
            hotkey_linux.unregister_hotkey()
        notifier.setEnabled.assert_called_once_with(False)
        fake.XCloseDisplay.assert_called_once()
        assert_that(hotkey_linux._state.display).is_none()
        assert_that(hotkey_linux._state.callback).is_none()

    def test_unregister_when_idle(self, hotkey_linux):
        fake = MagicMock()
        with patch.object(hotkey_linux, "_xlib", fake):
            hotkey_linux.unregister_hotkey()  # nothing registered
        fake.XCloseDisplay.assert_not_called()

    def test_load_xlib_missing_library(self, hotkey_linux):
        with patch("ctypes.CDLL", side_effect=OSError):
            assert_that(hotkey_linux._load_xlib()).is_none()
