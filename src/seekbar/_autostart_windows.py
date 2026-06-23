import sys

if sys.platform != "win32":  # pragma: no cover - Windows-only module
    msg = "This module is only available on Windows"
    raise ImportError(msg)

import contextlib
import subprocess
import winreg

from seekbar.autostart import _APP_NAME, _launch_argv

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
    except OSError:
        return False
    return True


def set_enabled(enabled: bool) -> None:  # noqa: FBT001 - simple on/off toggle
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(_launch_argv()))
        else:
            # already absent - disabling is idempotent
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, _APP_NAME)
