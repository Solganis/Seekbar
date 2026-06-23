import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from assertpy2 import assert_that

from seekbar import autostart


class TestLaunchArgv:
    def test_frozen_returns_executable_only(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("seekbar.autostart.sys", SimpleNamespace(frozen=True, executable="/app/Seekbar"))
        assert_that(autostart._launch_argv()).is_equal_to(["/app/Seekbar"])

    def test_dev_returns_module_invocation(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("seekbar.autostart.sys", SimpleNamespace(executable="/usr/bin/python"))
        assert_that(autostart._launch_argv()).is_equal_to(["/usr/bin/python", "-m", "seekbar"])


def _inject_fake_backend(monkeypatch: pytest.MonkeyPatch, name: str, **attrs: object) -> None:
    fake = types.ModuleType(name)
    fake.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, fake)


class TestDispatch:
    @pytest.mark.parametrize(
        ("platform", "module"),
        [
            ("win32", "seekbar._autostart_windows"),
            ("darwin", "seekbar._autostart_macos"),
            ("linux", "seekbar._autostart_linux"),
        ],
    )
    def test_is_enabled_dispatches(self, monkeypatch: pytest.MonkeyPatch, platform: str, module: str):
        monkeypatch.setattr("seekbar.autostart.sys", SimpleNamespace(platform=platform))
        _inject_fake_backend(monkeypatch, module, is_enabled=lambda: True)
        assert_that(autostart.is_enabled()).is_true()

    @pytest.mark.parametrize(
        ("platform", "module"),
        [
            ("win32", "seekbar._autostart_windows"),
            ("darwin", "seekbar._autostart_macos"),
            ("linux", "seekbar._autostart_linux"),
        ],
    )
    def test_set_enabled_dispatches(self, monkeypatch: pytest.MonkeyPatch, platform: str, module: str):
        monkeypatch.setattr("seekbar.autostart.sys", SimpleNamespace(platform=platform))
        calls: list[bool] = []
        _inject_fake_backend(monkeypatch, module, set_enabled=lambda enabled: calls.append(enabled))
        autostart.set_enabled(True)
        assert_that(calls).is_equal_to([True])

    def test_is_enabled_unsupported_returns_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("seekbar.autostart.sys", SimpleNamespace(platform="freebsd"))
        assert_that(autostart.is_enabled()).is_false()

    def test_set_enabled_unsupported_is_noop(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("seekbar.autostart.sys", SimpleNamespace(platform="freebsd"))
        autostart.set_enabled(True)  # must not raise


class TestImportGuards:
    @pytest.mark.parametrize(
        ("module", "needle"),
        [
            ("seekbar._autostart_windows", "Windows"),
            ("seekbar._autostart_macos", "macOS"),
            ("seekbar._autostart_linux", "Linux"),
        ],
    )
    def test_wrong_platform_raises(self, monkeypatch: pytest.MonkeyPatch, module: str, needle: str):
        foreign = "darwin" if needle == "Windows" else "win32"
        monkeypatch.setattr(sys, "platform", foreign)
        assert_that(lambda: importlib.reload(importlib.import_module(module))).raises(
            ImportError
        ).when_called_with().matches(needle)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
class TestAutostartWindows:
    def test_is_enabled_true_when_value_present(self):
        with patch("seekbar._autostart_windows.winreg"):
            from seekbar._autostart_windows import is_enabled  # noqa: PLC0415 - deferred; module has platform guard

            assert_that(is_enabled()).is_true()

    def test_is_enabled_false_on_missing_value(self):
        with patch("seekbar._autostart_windows.winreg") as mock_winreg:
            mock_winreg.QueryValueEx.side_effect = OSError
            from seekbar._autostart_windows import is_enabled  # noqa: PLC0415 - deferred; module has platform guard

            assert_that(is_enabled()).is_false()

    def test_set_enabled_true_writes_value(self):
        with patch("seekbar._autostart_windows.winreg") as mock_winreg:
            from seekbar._autostart_windows import set_enabled  # noqa: PLC0415 - deferred; module has platform guard

            set_enabled(True)
        mock_winreg.SetValueEx.assert_called_once()

    def test_set_enabled_false_deletes_value(self):
        with patch("seekbar._autostart_windows.winreg") as mock_winreg:
            from seekbar._autostart_windows import set_enabled  # noqa: PLC0415 - deferred; module has platform guard

            set_enabled(False)
        mock_winreg.DeleteValue.assert_called_once()

    def test_set_enabled_false_ignores_absent_value(self):
        with patch("seekbar._autostart_windows.winreg") as mock_winreg:
            mock_winreg.DeleteValue.side_effect = FileNotFoundError
            from seekbar._autostart_windows import set_enabled  # noqa: PLC0415 - deferred; module has platform guard

            set_enabled(False)  # must not raise


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")
class TestAutostartMacos:
    def test_enable_then_disable_lifecycle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from seekbar import _autostart_macos  # noqa: PLC0415 - deferred; module has platform guard

        assert_that(_autostart_macos.is_enabled()).is_false()
        _autostart_macos.set_enabled(True)
        assert_that(_autostart_macos.is_enabled()).is_true()
        assert_that(_autostart_macos._plist_path().read_bytes()).contains(b"RunAtLoad")
        _autostart_macos.set_enabled(False)
        assert_that(_autostart_macos.is_enabled()).is_false()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only")
class TestAutostartLinux:
    def test_enable_then_disable_lifecycle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from seekbar import _autostart_linux  # noqa: PLC0415 - deferred; module has platform guard

        assert_that(_autostart_linux.is_enabled()).is_false()
        _autostart_linux.set_enabled(True)
        assert_that(_autostart_linux.is_enabled()).is_true()
        assert_that(_autostart_linux._desktop_path().read_text(encoding="utf-8")).contains("[Desktop Entry]")
        _autostart_linux.set_enabled(False)
        assert_that(_autostart_linux.is_enabled()).is_false()
