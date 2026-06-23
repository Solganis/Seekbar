import sys

if sys.platform != "linux":  # pragma: no cover - Linux-only module
    msg = "This module is only available on Linux"
    raise ImportError(msg)

import shlex
from pathlib import Path

from seekbar.autostart import _APP_NAME, _launch_argv


def _desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / "seekbar.desktop"


def is_enabled() -> bool:
    return _desktop_path().exists()


def set_enabled(enabled: bool) -> None:  # noqa: FBT001 - simple on/off toggle
    path = _desktop_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={_APP_NAME}\n"
            f"Exec={shlex.join(_launch_argv())}\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        path.write_text(content, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
