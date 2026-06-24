import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest
from assertpy2 import assert_that


class TestImportGuard:
    def test_non_darwin_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert_that(lambda: importlib.reload(importlib.import_module("seekbar._hotkey_macos"))).raises(
            ImportError
        ).when_called_with().matches("macOS")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")
class TestHotkeyMacos:
    def test_register_success(self):
        from seekbar import _hotkey_macos  # noqa: PLC0415 - deferred; module has platform guard

        with patch.object(_hotkey_macos, "_carbon") as carbon:
            carbon.InstallEventHandler.return_value = 0
            carbon.RegisterEventHotKey.return_value = 0
            assert_that(_hotkey_macos.register_hotkey(MagicMock())).is_true()
        carbon.InstallEventHandler.assert_called_once()
        carbon.RegisterEventHotKey.assert_called_once()

    def test_register_fails_on_install_error(self):
        from seekbar import _hotkey_macos  # noqa: PLC0415 - deferred; module has platform guard

        with patch.object(_hotkey_macos, "_carbon") as carbon:
            carbon.InstallEventHandler.return_value = -1
            assert_that(_hotkey_macos.register_hotkey(MagicMock())).is_false()

    def test_register_fails_on_hotkey_error(self):
        from seekbar import _hotkey_macos  # noqa: PLC0415 - deferred; module has platform guard

        with patch.object(_hotkey_macos, "_carbon") as carbon:
            carbon.InstallEventHandler.return_value = 0
            carbon.RegisterEventHotKey.return_value = -1
            assert_that(_hotkey_macos.register_hotkey(MagicMock())).is_false()

    def test_handler_invokes_callback(self):
        from seekbar import _hotkey_macos  # noqa: PLC0415 - deferred; module has platform guard

        callback = MagicMock()
        with patch.object(_hotkey_macos, "_carbon") as carbon:
            carbon.InstallEventHandler.return_value = 0
            carbon.RegisterEventHotKey.return_value = 0
            _hotkey_macos.register_hotkey(callback)
        _hotkey_macos._keepalive[-1](0, 0, 0)
        callback.assert_called_once()

    def test_unregister(self):
        from seekbar import _hotkey_macos  # noqa: PLC0415 - deferred; module has platform guard

        with patch.object(_hotkey_macos, "_carbon") as carbon:
            _hotkey_macos.unregister_hotkey()
        carbon.UnregisterEventHotKey.assert_called_once()
        carbon.RemoveEventHandler.assert_called_once()
